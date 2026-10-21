"""Voice-requested local documents. Plain text -> DOCX/Markdown; never arbitrary paths or commands.

Installed on both the repository companion and the owner's newer panel through a
two-line hook. Display, microphone, mouse and normal conversation remain untouched.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path


def norm(text):
    value = unicodedata.normalize('NFKD', str(text).lower())
    return ''.join(c for c in value if not unicodedata.combining(c)).strip()


def english_request(text):
    return bool(re.search(r'\b(write|draft|create|prepare|expand|revise|rewrite|shorten|open|show|recover|retrieve|remember|add)\b', norm(text)))


def intent(text, has_document=False):
    # Whisper often writes "Jarvis." or "¿Jarvis, ...": any punctuation after the name is accepted.
    value = re.sub(r'^[\s¿¡]*(?:(?:oye|hey|please)[\s,]+)?jarvis\b[\s,.:;!?¿¡]*', '', norm(text))
    value = re.sub(r'^[\s¿¡]*(?:por favor|please)[\s,]+', '', value)
    value = re.sub(r'^[\s¿¡]*(?:puedes|podrias|can you|could you)\s+', '', value).lstrip(' ¿¡').rstrip(' .!?¿¡')
    verb = (r'(?:redacta(?:me)?|escribe(?:me)?|crea(?:me)?|prepara(?:me)?|haz(?:me)?|genera(?:me)?'
            r'|me (?:redactas|escribes|creas|preparas|haces|generas)'
            r'|(?:redactar|escribir|crear|preparar|hacer|generar)(?:me)?|write|draft|create|prepare)')
    match = re.fullmatch(r'(?:recuerda|remember) (?:para mis documentos|for my documents)\s*[:,]?\s+(.{3,300})', value)
    if match:
        return 'preference'
    if re.match(r'^' + verb + r'\b', value) and re.search(
            r'\b(monografia|ensayo|informe|documento|carta|propuesta|resumen|monograph|essay|report|document|letter|proposal)\b', value):
        return 'new'
    if re.fullmatch(r'(?:abre|abrir|open|muestra|show)(?: el| the)? (?:ultimo documento|documento|last document|document)', value):
        return 'open'
    if re.fullmatch(r'(?:recupera|recuperar|recover|retrieve)(?: el| the)? (?:documento pendiente|pending document)', value):
        return 'recover'
    if re.fullmatch(r'(?:descarta|discard)(?: el| the)? (?:documento pendiente|pending document)', value):
        return 'discard'
    if has_document and re.match(r'^(?:amplia|ampliame|corrige|revisa|reescribe|resume|acorta|anade|agrega|expand|revise|rewrite|shorten|add)\b', value) and re.search(
            r'\b(introduccion|conclusion|parrafo|seccion|documento|monografia|ensayo|informe|introduction|conclusion|paragraph|section|document|essay|report|it)\b', value):
        return 'revise'
    return None


def validate(document):
    if not isinstance(document, dict):
        raise ValueError('Documento inválido')
    out = {}
    for key, limit in (('title', 120), ('content', 20000), ('summary', 350)):
        value = document.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value):
            raise ValueError('Documento incompleto')
        out[key] = value.strip()
    return out


def _private_write(path, data):
    fd, name = tempfile.mkstemp(prefix='.jarvis-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def docx_bytes(document):
    import io
    paragraphs = []
    for line in ('# ' + document['title'] + '\n\n' + document['content']).splitlines():
        heading = re.match(r'^(#{1,3})\s+(.+)', line)
        style = '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>' if heading else ''
        value = heading[2] if heading else line
        formatting = '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr>' if heading else ''
        paragraphs.append('<w:p>' + style + '<w:r>' + formatting + '<w:t xml:space="preserve">' + html.escape(value) + '</w:t></w:r></w:p>')
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + ''.join(paragraphs) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
           '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', xml)
    return buf.getvalue()


class Store:
    def __init__(self, home):
        self.root = Path(home) / 'documentos'
        if self.root.is_symlink():
            raise ValueError('Carpeta de documentos inválida')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state = self.root / 'ultimo.json'
        self.pending_file = self.root / 'pendiente.json'

    def pending(self):
        if not self.pending_file.exists():
            return None
        if self.pending_file.is_symlink():
            raise ValueError('Registro pendiente inválido')
        value = json.loads(self.pending_file.read_text(encoding='utf-8'))
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', value):
            raise ValueError('Registro pendiente inválido')
        return value

    def set_pending(self, request_id):
        if self.pending_file.is_symlink():
            raise ValueError('Registro pendiente inválido')
        # Se valida al ESCRIBIR con la misma regla que al leer. Sin esto, un id que pending()
        # rechaza se quedaba guardado y dejaba el modulo trabado en TODAS las peticiones.
        if request_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', str(request_id)):
            raise ValueError('Identificador de turno inválido')
        _private_write(self.pending_file, json.dumps(request_id).encode())

    def latest(self):
        if not self.state.exists():
            return {}
        if self.state.is_symlink():
            raise ValueError('Registro de documentos inválido')
        data = json.loads(self.state.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Registro de documentos inválido')
        return data

    def preferences(self):
        values = self.latest().get('preferences', [])
        if not isinstance(values, list):
            raise ValueError('Preferencias inválidas')
        return [p for p in values if isinstance(p, str) and len(p) <= 300][-5:]

    def remember(self, request):
        preference = re.split(r'(?:para mis documentos|for my documents)\s*[:,]?\s*', request, maxsplit=1, flags=re.I)[-1].strip()
        if not preference or len(preference) > 300 or re.search(r'\b(?:token|password|contrase\w*|clave)\b|\bsk-', preference, re.I):
            raise ValueError('Guarda solo preferencias de redacción; no claves ni credenciales')
        data = self.latest(); prefs = self.preferences()
        if preference not in prefs:
            prefs = (prefs + [preference])[-5:]
        data['preferences'] = prefs
        _private_write(self.state, json.dumps(data, ensure_ascii=False).encode())

    def save(self, request_id, document):
        document = validate(document)
        name = 'documento-' + hashlib.sha256(request_id.encode()).hexdigest()[:16]
        docx = self.root / (name + '.docx'); markdown = self.root / (name + '.md')
        raw = ('# ' + document['title'] + '\n\n' + document['content'] + '\n').encode()
        if docx.is_symlink() or markdown.is_symlink():
            raise ValueError('Ruta de documento inválida')
        if markdown.exists():
            if markdown.read_bytes() != raw or not docx.is_file():
                raise ValueError('Ese turno ya tiene otro contenido; no sobrescribo el documento')
        else:
            _private_write(docx, docx_bytes(document)); _private_write(markdown, raw)
        prior = self.latest()
        data = {'document': document, 'file': docx.name, 'preferences': self.preferences(),
                'version': int(prior.get('version', 0)) + (prior.get('file') != docx.name)}
        _private_write(self.state, json.dumps(data, ensure_ascii=False).encode())
        return docx

    def last_path(self):
        name = self.latest().get('file', '')
        if not re.fullmatch(r'documento-[a-f0-9]{16}\.docx', name):
            raise ValueError('Todavía no hay un documento guardado')
        path = self.root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('El documento no está disponible')
        return path


def open_document(path):
    if sys.platform != 'darwin':
        return False
    try:
        return subprocess.run(['open', str(path)], check=False, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def install(companion):
    if getattr(companion, '_documentos_installed', False):
        return
    original = companion._run_turn

    def run(self, tid, text):
        with self.lock:
            if self.turns.get(tid, {}).get("cancelled"):
                return
        # Inspect only explicit document requests, never intercept normal conversation.
        value = intent(text, has_document=True)
        if value is None:
            return original(self, tid, text)
        english = english_request(text)
        def say(es, en):
            return en if english else es
        try:
            store = Store(self.home)
            previous = store.latest().get('document')
            value = intent(text, has_document=bool(previous))
            if value is None:
                return original(self, tid, text)
            if value == 'preference':
                store.remember(text)
                return self._finish(tid, 'done', say('Recordaré esa preferencia para tus próximos documentos.', 'I will remember that preference for your next documents.'))
            if value == 'discard':
                store.set_pending(None)
                return self._finish(tid, 'done', say('Quité el pendiente local. Los documentos guardados se conservan.', 'I cleared the pending request locally. Your saved documents are preserved.'))
            if value == 'open':
                try:
                    path = store.last_path()
                except ValueError:
                    return self._finish(tid, 'done', say('Todavía no tienes un documento guardado. Pídeme que redacte uno.', "You do not have a saved document yet. Ask me to write one."))
                opened = open_document(path)
                return self._finish(tid, 'done', say('Abrí el último documento.', 'I opened your last document.') if opened else say('El documento está guardado, pero no pude abrirlo.', 'Your document is saved, but I could not open it.'))
            if self.demo or not self.client.url or not self._token():
                return self._finish(tid, 'error', say('Necesito la conexión real con Jarvis para redactar el documento.', 'I need the live connection to Jarvis to write the document.'))
            with self.lock:
                self.turns[tid]['state'] = 'consultando'
            self.emit({'type': 'state', 'state': 'consultando', 'turn': tid})
            request_id = tid
            if value == 'recover':
                request_id = store.pending()
                if not request_id:
                    return self._finish(tid, 'done', say('No hay un documento pendiente de recuperar.', 'There is no pending document to recover.'))
                result = self.client._call('POST', '/desktop/v1/documents/get', {'request_id': request_id})
            else:
                if store.pending():
                    return self._finish(tid, 'error', say('Hay una redacción sin confirmar. Di: recupera el documento pendiente.', 'A draft is still unconfirmed. Say: recover the pending document.'))
                body = {'request_id': tid, 'text': text, 'preferences': store.preferences(),
                        'previous': previous if value == 'revise' else None}
                store.set_pending(tid)
                result = self.client._call('POST', '/desktop/v1/documents', body)
            if result.get('state') != 'done' or not result.get('document'):
                if result.get('state') == 'error':
                    store.set_pending(None)
                return self._finish(tid, 'error', result.get('reply') or say('La redacción sigue sin confirmar. Di: recupera el documento pendiente.', 'The draft is still unconfirmed. Say: recover the pending document.'))
            with self.lock:
                if self.turns[tid].get('cancelled'):
                    return
                path = store.save(request_id, result['document'])
                store.set_pending(None)
            with self.lock:
                if self.turns[tid].get('cancelled'):
                    return
            opened = open_document(path)
            message = (say('Documento guardado y abierto: ', 'Document saved and opened: ') if opened else say('Documento guardado: ', 'Document saved: ')) + result['document']['title'] + '.'
            message += say(' Puedes pedirme que amplíe o corrija una sección.', 'You can ask me to expand or revise a section.')
            return self._finish(tid, 'done', message, llm=True)
        except Exception as exc:
            # Never speak exception text that may contain paths, credentials or provider bodies.
            if getattr(exc, 'status', None) in (400, 401, 403, 404, 429):
                store.set_pending(None)
            if hasattr(exc, 'status') and exc.status == 401:
                self._auth_lost(exc.detail)
            return self._finish(tid, 'error', say('No pude completar el documento. Conservé las versiones anteriores.', 'I could not complete the document. Your previous versions are preserved.'))

    companion._run_turn = run
    companion._documentos_installed = True
