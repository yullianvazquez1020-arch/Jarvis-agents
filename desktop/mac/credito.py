#!/usr/bin/env python3
"""El mejor camino local para el crédito: ordenar, no inventar.

No entra a centrales ni a bancos, no guarda números y no envía la carta.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from agent_executor import control_dir, denial

CENTRALES = {"equifax", "experian", "transunion"}
TIPOS = {
    "no-reconozco": "No reconozco esta cuenta.",
    "ya-pague": "Esta cuenta ya está pagada y el informe sigue mostrándola abierta.",
    "fecha-mal": "La fecha que aparece no corresponde.",
    "duplicada": "Esta misma cuenta está repetida.",
    "saldo-mal": "El saldo que aparece no es el correcto.",
    "consulta": "No autoricé esta consulta.",
}
NUMERO = re.compile(r"\d{4,}")
PASOS = (
    "1. Abre tú annualcreditreport.com y baja los tres informes. Jarvis no entra.",
    "2. Separa dos pilas: errores reales, y cuentas que sí son tuyas.",
    "3. Anota cada error con su tipo. Sin números de cuenta.",
    "4. Saca la carta, complétala a mano y la envías tú a cada central que la muestre.",
    "5. Márcala enviada aquí. A los 30 días revisas si la corrigieron.",
    "6. Lo que sí es tuyo no se disputa: se paga a tiempo y se baja de 30% el uso.",
)


def hoy() -> datetime:
    return datetime.now(timezone.utc)


def limpiar(motivo: str) -> str:
    text = " ".join(motivo.split())
    if len(text) > 160 or NUMERO.search(text) or denial({"action": "type", "text": text}):
        raise ValueError("dato")
    return text


def ruta():
    return control_dir() / "credito.jsonl"


def lista() -> list[dict]:
    path = ruta()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def guardar(notes: list[dict]) -> None:
    ruta().write_text("".join(json.dumps(note, ensure_ascii=False) + "\n" for note in notes), encoding="utf-8")


def anotar(central: str, motivo: str = "", tipo: str = "no-reconozco") -> list[dict]:
    if tipo not in TIPOS:
        raise ValueError("tipo")
    text = limpiar(motivo) if motivo.strip() else ""
    centrales = list(CENTRALES) if central == "todas" else [central]
    if any(item not in CENTRALES for item in centrales):
        raise ValueError("central")
    created = []
    for item in centrales:
        created.append({
            "central": item,
            "tipo": tipo,
            "motivo": text or TIPOS[tipo],
            "at": hoy().isoformat(),
            "enviado": False,
            "vence": "",
        })
    notes = lista()
    notes.extend(created)
    guardar(notes)
    return created


def carta(note: dict) -> str:
    return "\n".join([
        "[Tu nombre]",
        "[Tu dirección en Puerto Rico]",
        "[Fecha]",
        "",
        note["central"].title(),
        "Solicitud para corregir información inexacta",
        "",
        "Pido que investiguen este dato y lo corrijan o lo eliminen.",
        f"Motivo: {note['motivo']}",
        "Adjunto la página del informe donde se ve. El número de cuenta lo escribo a mano en esa copia, no en este archivo.",
        "Espero la respuesta por escrito.",
        "",
        "[Tu firma]",
        "",
        "Jarvis no envía esta carta. La envías tú.",
    ])


def marcar(indice: int, cuando: datetime | None = None) -> dict:
    notes = lista()
    if not 1 <= indice <= len(notes):
        raise ValueError("id")
    note = notes[indice - 1]
    momento = cuando or hoy()
    note["enviado"] = True
    note["vence"] = (momento.date() + timedelta(days=30)).isoformat()
    notes[indice - 1] = note
    guardar(notes)
    return note


def plan(notes: list[dict] | None = None) -> str:
    notes = lista() if notes is None else notes
    abiertas = [note for note in notes if not note.get("enviado")]
    vencidas = [note for note in notes if note.get("enviado") and note.get("vence") and note["vence"] <= hoy().date().isoformat()]
    lineas = [
        "Orden que sí mueve el puntaje:",
        "1. Errores que no son tuyos: disputarlos, una vez, con el informe.",
        "2. Pagos a tiempo. Un atraso reciente pesa más que una carta.",
        "3. Uso de tarjetas por debajo de 30%. Eso se hace pagando, no disputando.",
        "4. No abrir cuentas nuevas para 'reparar' el crédito.",
    ]
    if abiertas:
        lineas.append(f"Tienes {len(abiertas)} error(es) anotados y todavía no marcados como enviados.")
    else:
        lineas.append("No hay disputas pendientes. Si el informe está bien, otra carta no sube el puntaje.")
    if vencidas:
        lineas.append(f"{len(vencidas)} respuesta(s) ya cumplieron 30 días: vuelve a mirar el informe.")
    lineas.append("Una cuenta que sí es tuya no se disputa.")
    return "\n".join(lineas)


def self_test() -> int:
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
        assert denial({"action": "open_url", "url": "https://www.equifax.com/login"}) == "denylist"
        created = anotar("equifax", "Cuenta que no reconozco")
        assert created[0]["enviado"] is False
        assert lista()[0]["motivo"] == "Cuenta que no reconozco"
        texto = carta(lista()[0])
        assert "Jarvis no envía" in texto and "123" not in texto
        note = marcar(1, datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert note["vence"] == "2026-01-31"
        assert "30 días" in plan() or "cumplieron 30" in plan()
        tres = anotar("todas", tipo="ya-pague")
        assert len(tres) == 3
        try:
            anotar("experian", "ssn 123-45-6789")
        except ValueError:
            pass
        else:
            raise SystemExit("acepto un numero")
        try:
            anotar("banco", "algo")
        except ValueError:
            pass
        else:
            raise SystemExit("acepto un banco")
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Crédito local. Sin cuentas y sin enviar cartas.")
    parser.add_argument("--pasos", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--anotar", action="store_true")
    parser.add_argument("--central", default="")
    parser.add_argument("--tipo", default="no-reconozco")
    parser.add_argument("--motivo", default="")
    parser.add_argument("--lista", action="store_true")
    parser.add_argument("--carta", type=int, default=0)
    parser.add_argument("--enviado", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.anotar:
        try:
            created = anotar(args.central, args.motivo, args.tipo)
        except ValueError:
            print("No guardé eso. Central válida, tipo válido, y ningún número.")
            return 2
        print(f"Anotadas {len(created)}, sin enviar.")
        return 0
    if args.carta:
        notes = lista()
        if not 1 <= args.carta <= len(notes):
            print("No hay esa nota.")
            return 2
        print(carta(notes[args.carta - 1]))
        return 0
    if args.enviado:
        try:
            note = marcar(args.enviado)
        except ValueError:
            print("No hay esa nota.")
            return 2
        print(f"La marcaste enviada. Revísala el {note['vence']}. Jarvis no la mandó.")
        return 0
    if args.lista:
        for index, note in enumerate(lista(), 1):
            estado = note["vence"] if note.get("enviado") else "sin enviar"
            print(f"{index}. {note['central']} {note['tipo']}: {note['motivo']} ({estado})")
        return 0
    if args.pasos:
        print("\n".join(PASOS))
        return 0
    print(plan())
    print()
    print("\n".join(PASOS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
