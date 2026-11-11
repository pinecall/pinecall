/** The cards a Studio tool is edited in: its settings, its parameters, headers, static fields, authorization and what it says. */

import { useState, type ReactNode } from "react";

import { type FixedField, type HttpTool, type Param } from "./door";
import { aParam, authOf, DELAYED_AFTER_S, fixedValueOf, LONGEST_S, METHODS, PARAM_TYPES, paramsOf, replaced, schemaOf, withAuth, without, type AuthScheme } from "./tool-shape";

const LONGEST_DESCRIPTION = 1000;

/** One collapsible card: a title, a line under it, and its body. */
export function Card({ title, about, open = true, children }: { title: string; about: string; open?: boolean; children: ReactNode }): ReactNode {
  const [shown, setShown] = useState(open);
  return (
    <section className="tl-card" aria-label={title}>
      <button type="button" className="tl-card-top" aria-expanded={shown} onClick={() => setShown((was) => !was)}>
        <span className="tl-card-words">
          <span className="tl-card-title">{title}</span>
          <span className="dash-quiet">{about}</span>
        </span>
        <svg className={shown ? "tl-chevron tl-chevron-open" : "tl-chevron"} aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {shown && <div className="tl-card-body">{children}</div>}
    </section>
  );
}

function Field({ label, hint, counted, children }: { label: string; hint?: string | undefined; counted?: string | undefined; children: ReactNode }): ReactNode {
  return (
    <label className="tl-field">
      <span className="tl-field-top">
        <span className="tl-field-label">{label}</span>
        {counted !== undefined && <span className="dash-quiet">{counted}</span>}
      </span>
      {children}
      {hint !== undefined && <span className="dash-quiet">{hint}</span>}
    </label>
  );
}

function Toggle({ on, label, disabled, onChange }: { on: boolean; label: string; disabled: boolean; onChange: (on: boolean) => void }): ReactNode {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={on ? "kn-toggle kn-toggle-on" : "kn-toggle"} disabled={disabled} onClick={() => onChange(!on)}>
      <span className="kn-knob" />
    </button>
  );
}

export function Drop({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }): ReactNode {
  return (
    <button type="button" className="kn-drop" aria-label={label} disabled={disabled} onClick={onClick}>
      ×
    </button>
  );
}

export function More({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }): ReactNode {
  if (disabled) return null;
  return (
    <button type="button" className="tl-more" onClick={onClick}>
      + {label}
    </button>
  );
}

// ── Tool settings ──

export function SettingsCard({ tool, readOnly, wrong, onChange }: { tool: HttpTool; readOnly: boolean; wrong: string | null; onChange: (tool: HttpTool) => void }): ReactNode {
  return (
    <Card title="Tool settings" about="What the model reads to decide when to call it, and where the request goes.">
      <Field label="Tool name">
        <input className="cfg-input tl-mono" aria-label="Tool name" spellCheck={false} value={tool.name} disabled={readOnly} onChange={(event) => onChange({ ...tool, name: event.target.value })} />
      </Field>
      {wrong !== null && <p className="cfg-refused">{wrong}</p>}
      <Field label="Description" counted={`${tool.description.length}/${LONGEST_DESCRIPTION}`}>
        <textarea className="cfg-input cfg-area" rows={3} maxLength={LONGEST_DESCRIPTION} placeholder="Looks up an order by its number and answers its status." value={tool.description} readOnly={readOnly} onChange={(event) => onChange({ ...tool, description: event.target.value })} />
      </Field>
      <div className="tl-request">
        <Field label="Method">
          <select className="cfg-input" aria-label="Method" value={tool.method} disabled={readOnly} onChange={(event) => onChange({ ...tool, method: event.target.value as HttpTool["method"] })}>
            {METHODS.map((method) => (
              <option key={method}>{method}</option>
            ))}
          </select>
        </Field>
        <Field label="Request URL" hint="HTTPS only. {name} in the path is filled from the parameter of that name.">
          <input className="cfg-input tl-mono" aria-label="URL" placeholder="https://api.example.com/orders/{order_id}" spellCheck={false} value={tool.url} disabled={readOnly} onChange={(event) => onChange({ ...tool, url: event.target.value })} />
        </Field>
      </div>
      <Field label="Waits at most" hint={`Seconds before the request is given up, ${LONGEST_S} at most.`}>
        <input
          className="cfg-input tl-short"
          type="number"
          min={1}
          max={LONGEST_S}
          aria-label="Timeout in seconds"
          value={tool.timeout_s}
          disabled={readOnly}
          onChange={(event) => {
            const seconds = event.target.valueAsNumber;
            if (Number.isFinite(seconds)) onChange({ ...tool, timeout_s: seconds });
          }}
        />
      </Field>
    </Card>
  );
}

// ── Parameters ──

function EnumValues({ param, readOnly, onChange }: { param: Param; readOnly: boolean; onChange: (param: Param) => void }): ReactNode {
  const values = param.enum ?? [];
  const [typed, setTyped] = useState("");
  const add = (): void => {
    const word = typed.trim();
    if (word === "" || values.includes(word)) return;
    onChange({ ...param, enum: [...values, word] });
    setTyped("");
  };
  return (
    <div className="tl-enum">
      <span className="tl-field-label">Allowed values</span>
      {values.length === 0 ? (
        <span className="dash-quiet tl-enum-none">Any text. Add values to make it a closed list the model picks from.</span>
      ) : (
        <div className="tl-chips">
          {values.map((value) => (
            <span key={value} className="tl-chip">
              {value}
              {!readOnly && <Drop label={`Remove ${value}`} disabled={false} onClick={() => onChange({ ...param, enum: values.length === 1 ? null : values.filter((one) => one !== value) })} />}
            </span>
          ))}
        </div>
      )}
      {!readOnly && (
        <div className="tl-enum-add">
          <input
            className="cfg-input tl-short"
            aria-label="New value"
            placeholder="Add a value"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              }
            }}
          />
          <button type="button" className="app-button" disabled={typed.trim() === ""} onClick={add}>
            Add value
          </button>
        </div>
      )}
    </div>
  );
}

function ParamCard({ param, readOnly, onChange, onRemove }: { param: Param; readOnly: boolean; onChange: (param: Param) => void; onRemove: () => void }): ReactNode {
  return (
    <div className="tl-param">
      <div className="tl-param-top">
        <Field label="Name">
          <input className="cfg-input tl-mono" aria-label="Parameter name" placeholder="order_id" spellCheck={false} value={param.name} disabled={readOnly} onChange={(event) => onChange({ ...param, name: event.target.value })} />
        </Field>
        <Field label="Type">
          <select className="cfg-input" aria-label="Type" value={param.type} disabled={readOnly} onChange={(event) => onChange({ ...param, type: event.target.value as Param["type"], enum: event.target.value === "string" ? param.enum : null })}>
            {PARAM_TYPES.map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
        </Field>
        <div className="tl-param-side">
          <label className="tl-check">
            <input type="checkbox" checked={param.required} disabled={readOnly} onChange={(event) => onChange({ ...param, required: event.target.checked })} />
            Required
          </label>
          {!readOnly && <Drop label={`Remove ${param.name || "parameter"}`} disabled={false} onClick={onRemove} />}
        </div>
      </div>
      <Field label="Description">
        <textarea className="cfg-input cfg-area" rows={2} placeholder="What it is, as the model reads it (optional)" value={param.description} readOnly={readOnly} onChange={(event) => onChange({ ...param, description: event.target.value })} />
      </Field>
      {param.type === "string" && <EnumValues param={param} readOnly={readOnly} onChange={onChange} />}
    </div>
  );
}

function JsonParams({ params, readOnly, onChange }: { params: Param[]; readOnly: boolean; onChange: (params: Param[]) => void }): ReactNode {
  const [text, setText] = useState(() => JSON.stringify(schemaOf(params), null, 2));
  const [refused, setRefused] = useState<string | null>(null);
  const apply = (): void => {
    const read = paramsOf(text);
    if ("refused" in read) return setRefused(read.refused);
    setRefused(null);
    onChange(read.params);
    setText(JSON.stringify(schemaOf(read.params), null, 2));
  };
  return (
    <div className="tl-json">
      <textarea className="cfg-input cfg-area tl-code" rows={Math.min(24, Math.max(8, text.split("\n").length + 1))} spellCheck={false} aria-label="Parameters as JSON Schema" value={text} readOnly={readOnly} onChange={(event) => setText(event.target.value)} />
      {refused !== null && <p className="cfg-refused">{refused}</p>}
      {!readOnly && (
        <div className="tl-json-foot">
          <span className="dash-quiet">An object schema of strings, numbers, integers and booleans; a string may carry an enum. Nothing nested.</span>
          <button type="button" className="app-button" onClick={apply}>
            Apply JSON
          </button>
        </div>
      )}
    </div>
  );
}

export function ParamsCard({ params, readOnly, onChange }: { params: Param[]; readOnly: boolean; onChange: (params: Param[]) => void }): ReactNode {
  const [view, setView] = useState<"visual" | "json">("visual");
  return (
    <Card title="Parameters" about="What the model fills in. {name} in the URL takes the path; the rest go in the query of a GET or DELETE, else the JSON body.">
      <div className="tl-params-top">
        <div className="dash-switch" role="tablist" aria-label="Parameters view">
          <button type="button" role="tab" aria-selected={view === "visual"} className={view === "visual" ? "dash-switch-on" : ""} onClick={() => setView("visual")}>
            Visual
          </button>
          <button type="button" role="tab" aria-selected={view === "json"} className={view === "json" ? "dash-switch-on" : ""} onClick={() => setView("json")}>
            JSON
          </button>
        </div>
        <span className="dash-quiet">The schema is locked: an argument the model invents is dropped.</span>
      </div>
      {view === "json" ? (
        <JsonParams key={JSON.stringify(params)} params={params} readOnly={readOnly} onChange={onChange} />
      ) : (
        <div className="tl-rows">
          {params.map((param, at) => (
            <ParamCard key={at} param={param} readOnly={readOnly} onChange={(next) => onChange(replaced(params, at, next))} onRemove={() => onChange(without(params, at))} />
          ))}
          {params.length === 0 && <p className="dash-quiet">No parameters: the model calls it with nothing.</p>}
          <More label="Add parameter" disabled={readOnly} onClick={() => onChange([...params, aParam()])} />
        </div>
      )}
    </Card>
  );
}

// ── Headers, static fields, authorization ──

export function HeadersCard({ tool, readOnly, onChange }: { tool: HttpTool; readOnly: boolean; onChange: (headers: HttpTool["headers"]) => void }): ReactNode {
  const auth = authOf(tool);
  const plain = tool.headers.map((header, at) => ({ header, at })).filter(({ header }) => !(auth.scheme !== "none" && header.name === auth.header && header.value.includes(`{{secrets.${auth.secret}}}`)));
  return (
    <Card title="Request headers" about="Sent with every request. Authorization has a card of its own below." open={plain.length > 0}>
      <div className="tl-rows">
        {plain.map(({ header, at }) => (
          <div key={at} className="tl-row tl-row-pair">
            <input className="cfg-input tl-mono" aria-label="Header name" placeholder="X-Source" spellCheck={false} value={header.name} disabled={readOnly} onChange={(event) => onChange(replaced(tool.headers, at, { ...header, name: event.target.value }))} />
            <input className="cfg-input tl-mono" aria-label="Header value" placeholder="phone" spellCheck={false} value={header.value} disabled={readOnly} onChange={(event) => onChange(replaced(tool.headers, at, { ...header, value: event.target.value }))} />
            {!readOnly && <Drop label={`Remove ${header.name || "header"}`} disabled={false} onClick={() => onChange(without(tool.headers, at))} />}
          </div>
        ))}
        {plain.length === 0 && <p className="dash-quiet">None.</p>}
        <More label="Add header" disabled={readOnly} onClick={() => onChange([...tool.headers, { name: "", value: "" }])} />
      </div>
    </Card>
  );
}

export function FixedCard({ fixed, readOnly, onChange }: { fixed: FixedField[]; readOnly: boolean; onChange: (fixed: FixedField[]) => void }): ReactNode {
  return (
    <Card title="Static fields" about="Sent with every request beside the model's arguments, set here and never by the model. A value may name the call: {{call.from}}." open={fixed.length > 0}>
      <div className="tl-rows">
        {fixed.map((field, at) => (
          <div key={at} className="tl-row tl-row-pair">
            <input className="cfg-input tl-mono" aria-label="Field name" placeholder="source" spellCheck={false} value={field.name} disabled={readOnly} onChange={(event) => onChange(replaced(fixed, at, { ...field, name: event.target.value }))} />
            <input className="cfg-input tl-mono" aria-label="Field value" placeholder="phone" spellCheck={false} value={String(field.value)} disabled={readOnly} onChange={(event) => onChange(replaced(fixed, at, { ...field, value: fixedValueOf(event.target.value) }))} />
            {!readOnly && <Drop label={`Remove ${field.name || "field"}`} disabled={false} onClick={() => onChange(without(fixed, at))} />}
          </div>
        ))}
        {fixed.length === 0 && <p className="dash-quiet">None.</p>}
        <More label="Add field" disabled={readOnly} onClick={() => onChange([...fixed, { name: "", value: "" }])} />
      </div>
    </Card>
  );
}

export function AuthCard({ tool, secrets, readOnly, onChange }: { tool: HttpTool; secrets: readonly string[]; readOnly: boolean; onChange: (headers: HttpTool["headers"]) => void }): ReactNode {
  const auth = authOf(tool);
  const [header, setHeader] = useState(auth.header);
  const set = (scheme: AuthScheme, secret: string, name: string): void => onChange(withAuth(tool, scheme, secret, name));
  const options = secrets.includes(auth.secret) || auth.secret === "" ? secrets : [auth.secret, ...secrets];
  return (
    <Card title="Authorization" about="A secret of the org's, sent in a header. The secret itself never enters the definition." open={auth.scheme !== "none"}>
      <div className="tl-auth">
        <Field label="Scheme">
          <select className="cfg-input" aria-label="Authorization scheme" value={auth.scheme} disabled={readOnly} onChange={(event) => set(event.target.value as AuthScheme, auth.secret || (secrets[0] ?? ""), header)}>
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="header">API key in a header</option>
          </select>
        </Field>
        {auth.scheme !== "none" && (
          <Field label="Secret" hint={secrets.length === 0 ? "No secret set yet: Settings ▸ Secrets, or `pinecall secrets set`." : undefined}>
            <select className="cfg-input tl-mono" aria-label="Secret" value={auth.secret} disabled={readOnly} onChange={(event) => set(auth.scheme, event.target.value, header)}>
              {auth.secret === "" && <option value="">Pick one</option>}
              {options.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {auth.scheme === "header" && (
          <Field label="Header">
            <input
              className="cfg-input tl-mono"
              aria-label="Header name"
              spellCheck={false}
              value={header}
              disabled={readOnly}
              onChange={(event) => setHeader(event.target.value)}
              onBlur={() => set("header", auth.secret, header)}
            />
          </Field>
        )}
      </div>
      {auth.scheme !== "none" && auth.secret !== "" && (
        <p className="dash-quiet">
          Sent as <code className="tl-code-inline">{auth.scheme === "bearer" ? `Authorization: Bearer {{secrets.${auth.secret}}}` : `${header}: {{secrets.${auth.secret}}}`}</code>, the value filled when the request goes.
        </p>
      )}
    </Card>
  );
}

// ── Messages ──

function Line({ label, hint, value, readOnly, placeholder, onChange }: { label: string; hint: string; value: string | null | undefined; readOnly: boolean; placeholder: string; onChange: (value: string | null) => void }): ReactNode {
  return (
    <Field label={label} hint={hint}>
      <input className="cfg-input" aria-label={label} placeholder={placeholder} value={value ?? ""} disabled={readOnly} onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)} />
    </Field>
  );
}

export function MessagesCard({ tool, readOnly, onChange }: { tool: HttpTool; readOnly: boolean; onChange: (tool: HttpTool) => void }): ReactNode {
  const said = Boolean(tool.announce || tool.delayed || tool.failed);
  return (
    <Card title="Messages" about="What the caller hears around the request. Left empty, the model finds its own words." open={said}>
      <Line label="Request start" hint="Said as the request starts, unless the agent already said something this turn." value={tool.announce} readOnly={readOnly} placeholder="One moment, let me check that." onChange={(announce) => onChange({ ...tool, announce })} />
      <div className="tl-delayed">
        <Line label="Request delayed" hint="Said once the request has run this long with no answer." value={tool.delayed} readOnly={readOnly} placeholder="Still checking, one moment." onChange={(delayed) => onChange({ ...tool, delayed })} />
        <Field label="After (s)">
          <input
            className="cfg-input tl-short"
            type="number"
            min={1}
            max={LONGEST_S}
            aria-label="Delayed after seconds"
            value={tool.delayed_after_s}
            disabled={readOnly || !tool.delayed}
            onChange={(event) => {
              const seconds = event.target.valueAsNumber;
              onChange({ ...tool, delayed_after_s: Number.isFinite(seconds) ? seconds : DELAYED_AFTER_S });
            }}
          />
        </Field>
      </div>
      <Line label="Request failed" hint="Said when the request failed, before the model reads why and answers." value={tool.failed} readOnly={readOnly} placeholder="I could not reach that just now." onChange={(failed) => onChange({ ...tool, failed })} />
      <div className="tl-switches">
        <div className="tl-switch">
          <span>
            <span className="tl-field-label">Lock schema</span>
            <span className="dash-quiet">Always on: an argument the model invents is dropped before the request.</span>
          </span>
          <Toggle on label="Lock schema" disabled onChange={() => undefined} />
        </div>
      </div>
    </Card>
  );
}
