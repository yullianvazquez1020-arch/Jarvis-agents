import { createFileRoute } from "@tanstack/react-router";
import { BookOpen, MousePointer2, Scale, Shield } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import {
  CENTRALES,
  ORDENES,
  TEMAS,
  TIPOS,
  carta,
  motivoLimpio,
  venceEn,
  type Nota,
  type Orden,
} from "@/lib/desk";

export const Route = createFileRoute("/")({ component: Home });

type Vista = "mouse" | "estudio" | "credito" | "reglas";
const CLAVE = "jarvis-desk-v1";

function Home() {
  const [vista, setVista] = useState<Vista>("mouse");
  const [vistos, setVistos] = useState<string[]>([]);
  const [notas, setNotas] = useState<Nota[]>([]);
  const [central, setCentral] = useState<(typeof CENTRALES)[number]>("equifax");
  const [tipo, setTipo] = useState<(typeof TIPOS)[number]["id"]>("no-reconozco");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState("");
  const [cartaId, setCartaId] = useState<string | null>(null);
  const [listo, setListo] = useState(false);
  const [ordenes, setOrdenes] = useState<Orden[]>([]);
  const [listas, setListas] = useState<string[]>(() =>
    ORDENES.filter((orden) => !orden.bloqueada).map((orden) => orden.linea),
  );
  const [aviso, setAviso] = useState(
    "Las cuatro órdenes están confirmadas. El banco no. El parche espera a Codex en el PR 32. No está fusionado.",
  );

  useEffect(() => {
    const guardado = localStorage.getItem(CLAVE);
    if (!guardado) {
      setListo(true);
      return;
    }
    try {
      const data = JSON.parse(guardado) as { vistos?: string[]; notas?: Nota[] };
      setVistos(data.vistos ?? []);
      setNotas(data.notas ?? []);
    } catch {
      localStorage.removeItem(CLAVE);
    }
    setListo(true);
  }, []);

  useEffect(() => {
    if (!listo) return;
    localStorage.setItem(CLAVE, JSON.stringify({ vistos, notas }));
  }, [listo, vistos, notas]);

  function anotar() {
    const limpio = motivoLimpio(motivo);
    if (motivo.trim() && limpio === null) {
      setError("Sin números de cuenta, sin claves y sin el nombre de un banco.");
      return;
    }
    setError("");
    const nota: Nota = {
      id: crypto.randomUUID(),
      central,
      tipo,
      motivo: limpio || TIPOS.find((item) => item.id === tipo)?.texto || "",
      enviado: false,
      vence: "",
    };
    setNotas((prev) => [nota, ...prev]);
    setMotivo("");
    setCartaId(nota.id);
  }

  const abierta = notas.find((nota) => nota.id === cartaId) ?? null;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-col gap-2">
        <p className="font-mono text-xs tracking-widest text-primary">ISLAFIX</p>
        <h1 className="text-3xl font-semibold">Jarvis</h1>
        <p className="max-w-xl text-muted">
          Jarvis, ChatGPT, Grok y Claude proponen el mouse. Tú confirmas. El banco no pasa.
        </p>
      </header>

      <nav className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Secciones">
        <Tab icon={<MousePointer2 size={18} />} activo={vista === "mouse"} onClick={() => setVista("mouse")}>
          Mouse
        </Tab>
        <Tab icon={<BookOpen size={18} />} activo={vista === "estudio"} onClick={() => setVista("estudio")}>
          Estudio
        </Tab>
        <Tab icon={<Scale size={18} />} activo={vista === "credito"} onClick={() => setVista("credito")}>
          Crédito
        </Tab>
        <Tab icon={<Shield size={18} />} activo={vista === "reglas"} onClick={() => setVista("reglas")}>
          Reglas
        </Tab>
      </nav>

      {vista === "mouse" && (
        <section className="flex flex-col gap-3">
          <p className="rounded-xl border border-border bg-surface p-4 text-sm">{aviso}</p>
          {ordenes.length === 0 && <p className="text-sm text-muted">No hay órdenes de mouse.</p>}
          {ordenes.map((orden, index) => {
            const turno = index === 0;
            return (
              <article key={orden.id} className="rounded-xl border border-border bg-surface p-4">
                <p className="font-mono text-xs tracking-widest text-primary">{orden.agente}</p>
                <p className="mt-2">{orden.detalle}</p>
                <p className="mt-1 text-sm text-muted">
                  {orden.bloqueada
                    ? "Bloqueada aunque confirmes."
                    : turno
                      ? "Tiene el turno. Espera tu confirmación."
                      : "Ocupado. Espera su turno."}
                </p>
                {turno && (
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      className="min-h-16 rounded-xl bg-primary font-medium text-primary-fg"
                      onClick={() => {
                        if (orden.bloqueada) {
                          setAviso("Bloqueada. El banco no se abre ni con confirmación.");
                          return;
                        }
                        setOrdenes((prev) => prev.filter((item) => item.id !== orden.id));
                        setListas((prev) => [...prev, orden.linea]);
                        setAviso("Confirmada una vez. Esa línea es la que ejecuta la Mac.");
                      }}
                    >
                      Confirmar
                    </button>
                    <button
                      type="button"
                      className="min-h-16 rounded-xl border border-border font-medium"
                      onClick={() => {
                        setOrdenes((prev) => prev.filter((item) => item.id !== orden.id));
                        setAviso("Cancelada. El turno pasa al siguiente.");
                      }}
                    >
                      Cancelar
                    </button>
                  </div>
                )}
              </article>
            );
          })}
          {listas.length > 0 && (
            <div className="rounded-xl border border-border p-4">
              <p className="text-sm font-medium">Listas para la Mac</p>
              <pre className="mt-2 overflow-x-auto font-mono text-sm whitespace-pre-wrap text-muted">
                {listas.join("\n")}
              </pre>
            </div>
          )}
        </section>
      )}

      {vista === "estudio" && (
        <section className="flex flex-col gap-3">
          <p className="text-sm text-muted">
            {vistos.length} de {TEMAS.length} temas repasados en este navegador.
          </p>
          {TEMAS.map((tema) => {
            const visto = vistos.includes(tema.id);
            return (
              <article key={tema.id} className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-lg font-medium">{tema.titulo}</h2>
                  <button
                    type="button"
                    className="min-h-11 rounded-lg bg-primary px-3 text-sm font-medium text-primary-fg"
                    onClick={() =>
                      setVistos((prev) =>
                        visto ? prev.filter((id) => id !== tema.id) : [...prev, tema.id],
                      )
                    }
                  >
                    {visto ? "Repasado" : "Marcar"}
                  </button>
                </div>
                <ul className="mt-3 flex flex-col gap-2 text-sm">
                  {tema.hechos.map((hecho) => (
                    <li key={hecho}>{hecho}</li>
                  ))}
                </ul>
              </article>
            );
          })}
        </section>
      )}

      {vista === "credito" && (
        <section className="flex flex-col gap-4">
          <ol className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-4 text-sm">
            <li>1. Errores que no son tuyos, una vez, con el informe.</li>
            <li>2. Pagar a tiempo pesa más que una carta.</li>
            <li>3. Bajar las tarjetas de 30% pagando, no disputando.</li>
            <li>4. No abras cuentas nuevas para reparar el crédito.</li>
          </ol>
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              anotar();
            }}
          >
            <label className="flex flex-col gap-1 text-sm">
              Central
              <select
                className="min-h-11 rounded-lg border border-border bg-bg px-3"
                value={central}
                onChange={(event) => setCentral(event.target.value as (typeof CENTRALES)[number])}
              >
                {CENTRALES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Tipo
              <select
                className="min-h-11 rounded-lg border border-border bg-bg px-3"
                value={tipo}
                onChange={(event) => setTipo(event.target.value as (typeof TIPOS)[number]["id"])}
              >
                {TIPOS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.texto}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Motivo, sin números
              <input
                className="min-h-11 rounded-lg border border-border bg-bg px-3"
                value={motivo}
                onChange={(event) => setMotivo(event.target.value)}
                placeholder="Cuenta que no reconozco"
              />
            </label>
            {error && <p className="text-sm text-warn">{error}</p>}
            <button type="submit" className="min-h-11 rounded-lg bg-primary font-medium text-primary-fg">
              Anotar sin enviar
            </button>
          </form>
          {notas.length === 0 && <p className="text-sm text-muted">Todavía no hay notas.</p>}
          {notas.map((nota) => (
            <article key={nota.id} className="rounded-xl border border-border bg-surface p-4 text-sm">
              <p className="font-medium">
                {nota.central} · {nota.enviado ? `revisar el ${nota.vence}` : "sin enviar"}
              </p>
              <p className="mt-1">{nota.motivo}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="min-h-11 rounded-lg border border-border px-3"
                  onClick={() => setCartaId(nota.id)}
                >
                  Ver carta
                </button>
                {!nota.enviado && (
                  <button
                    type="button"
                    className="min-h-11 rounded-lg border border-border px-3"
                    onClick={() =>
                      setNotas((prev) =>
                        prev.map((item) =>
                          item.id === nota.id ? { ...item, enviado: true, vence: venceEn(new Date()) } : item,
                        ),
                      )
                    }
                  >
                    Ya la envié yo
                  </button>
                )}
              </div>
            </article>
          ))}
          {abierta && (
            <pre className="overflow-x-auto rounded-xl border border-border bg-bg p-4 font-mono text-sm whitespace-pre-wrap">
              {carta(abierta)}
            </pre>
          )}
        </section>
      )}

      {vista === "reglas" && (
        <section className="flex flex-col gap-3">
          {TEMAS[0].hechos.map((hecho) => (
            <p key={hecho} className="rounded-xl border border-border bg-surface p-4">
              {hecho}
            </p>
          ))}
          <p className="text-sm text-muted">Estas reglas no se editan desde aquí.</p>
        </section>
      )}
    </main>
  );
}

function Tab({
  children,
  icon,
  activo,
  onClick,
}: {
  children: string;
  icon: ReactNode;
  activo: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-11 items-center justify-center gap-2 rounded-lg border px-2 text-sm font-medium ${
        activo ? "border-primary bg-primary text-primary-fg" : "border-border bg-surface text-fg"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}
