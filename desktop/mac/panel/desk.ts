export const TEMAS = [
  {
    id: "reglas",
    titulo: "Reglas",
    hechos: [
      "El tope es 100 dólares por operación y 300 dólares por día.",
      "Confirmar queda fuera de la cola y cada aprobación sirve una sola vez.",
      "La voz y el dictado son locales. No hay pagos reales ni mensajes a clientes.",
      "Nadie fusiona sin Codex y sin tu autorización.",
    ],
  },
  {
    id: "oficio",
    titulo: "Oficio",
    hechos: [
      "Un trabajo de ejemplo vale entre 40 y 95 dólares, nunca más de 100.",
      "Los estados son cotizado, aprobado, terminado, cobrado o cancelado.",
      "Antes de una ruta se mira el piso y los huecos de agenda.",
      "El precio se consulta. No se inventa un ingreso.",
    ],
  },
  {
    id: "credito",
    titulo: "Crédito",
    hechos: [
      "Los informes los bajas tú. Jarvis no entra a la central.",
      "Solo se disputa un error que no es tuyo.",
      "Un atraso reciente pesa más que una carta.",
      "Bajar las tarjetas de 30% se hace pagando, no disputando.",
    ],
  },
  {
    id: "mac",
    titulo: "Mac",
    hechos: [
      "Los agentes proponen el movimiento del mouse. Tú confirmas una vez.",
      "Un solo agente tiene el turno. Jarvis siempre pide confirmación.",
      "Bancos, pagos y centrales quedan bloqueados aunque confirmes.",
      "La tecla s, un código de un uso o el pulgar confirman. El puño cancela.",
    ],
  },
  {
    id: "voz",
    titulo: "Voz",
    hechos: [
      "La voz local es Piper en español.",
      "Cada nota vuelve a cargar el modelo. Por eso la primera tarda más.",
      "Una respuesta hablada se corta a 200 caracteres.",
      "No se usa un servicio de voz de pago.",
    ],
  },
] as const;

export const TIPOS = [
  { id: "no-reconozco", texto: "No reconozco esta cuenta." },
  { id: "ya-pague", texto: "Esta cuenta ya está pagada y el informe la sigue mostrando abierta." },
  { id: "fecha-mal", texto: "La fecha que aparece no corresponde." },
  { id: "duplicada", texto: "Esta misma cuenta está repetida." },
  { id: "saldo-mal", texto: "El saldo que aparece no es el correcto." },
  { id: "consulta", texto: "No autoricé esta consulta." },
] as const;

export const CENTRALES = ["equifax", "experian", "transunion"] as const;

const PROHIBIDO = /\d{4,}|equifax|experian|transunion|banco|paypal|coinbase/i;

export type Nota = {
  id: string;
  central: (typeof CENTRALES)[number];
  tipo: (typeof TIPOS)[number]["id"];
  motivo: string;
  enviado: boolean;
  vence: string;
};

export type Orden = {
  id: string;
  agente: "jarvis" | "grok" | "claude" | "chatgpt";
  detalle: string;
  bloqueada: boolean;
  linea: string;
};

export const ORDENES: Orden[] = [
  {
    id: "centro",
    agente: "jarvis",
    detalle: "Mover el puntero al centro de la pantalla.",
    bloqueada: false,
    linea: '{"agent":"jarvis","action":"move","x":720,"y":450}',
  },
  {
    id: "foto",
    agente: "chatgpt",
    detalle: "Tomar una captura de la pantalla.",
    bloqueada: false,
    linea: '{"agent":"chatgpt","action":"screenshot"}',
  },
  {
    id: "bajar",
    agente: "grok",
    detalle: "Bajar un poco la página.",
    bloqueada: false,
    linea: '{"agent":"grok","action":"scroll","dy":-3}',
  },
  {
    id: "espera",
    agente: "claude",
    detalle: "Esperar un segundo antes del siguiente movimiento.",
    bloqueada: false,
    linea: '{"agent":"claude","action":"wait","seconds":1}',
  },
  {
    id: "banco",
    agente: "claude",
    detalle: "Abrir el banco.",
    bloqueada: true,
    linea: "",
  },
];

export function motivoLimpio(valor: string): string | null {
  const texto = valor.trim().replace(/\s+/g, " ");
  if (texto.length > 160 || PROHIBIDO.test(texto)) return null;
  return texto;
}

export function fraseTipo(tipo: Nota["tipo"]): string {
  return TIPOS.find((item) => item.id === tipo)?.texto ?? TIPOS[0].texto;
}

export function carta(nota: Nota): string {
  return [
    "[Tu nombre]",
    "[Tu dirección en Puerto Rico]",
    "[Fecha]",
    "",
    nota.central[0].toUpperCase() + nota.central.slice(1),
    "Solicitud para corregir información inexacta",
    "",
    "Pido que investiguen este dato y lo corrijan o lo eliminen.",
    `Motivo: ${nota.motivo || fraseTipo(nota.tipo)}`,
    "El número de cuenta lo escribo a mano en la copia que yo envío.",
    "Espero la respuesta por escrito.",
    "",
    "[Tu firma]",
    "",
    "Jarvis no envía esta carta.",
  ].join("\n");
}

export function venceEn(desde: Date): string {
  const fecha = new Date(desde.getTime());
  fecha.setDate(fecha.getDate() + 30);
  return fecha.toISOString().slice(0, 10);
}
