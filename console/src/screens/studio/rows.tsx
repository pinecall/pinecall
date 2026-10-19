/** The editor's repeated rows: a request's headers, and the parameters a tool takes or the fields a call collects. */

import type { ReactNode } from "react";

import { Check, Input, Select, SelectItem, TextAction } from "../../ui";
import type { Header, Param, ParamType } from "./door";
import { aHeader, aParam, PARAM_TYPES, secretIn } from "./draft";

/** One list edited in place: the item at `at` replaced, or taken out. */
function replaced<T>(list: readonly T[], at: number, item: T): T[] {
  return list.map((one, index) => (index === at ? item : one));
}

function without<T>(list: readonly T[], at: number): T[] {
  return list.filter((_, index) => index !== at);
}

/** Headers a request carries, name and value; a value may name one of the env's secrets. */
export function HeaderRows({ headers, secrets, onChange }: { headers: Header[]; secrets: readonly string[]; onChange: (headers: Header[]) => void }): ReactNode {
  return (
    <div className="sto-rows">
      {headers.map((header, at) => (
        <div key={at} className="sto-row sto-row-header">
          <Input size="sm" value={header.name} placeholder="Authorization" aria-label="Header name" spellCheck={false} onChange={(event) => onChange(replaced(headers, at, { ...header, name: event.target.value }))} />
          <Input size="sm" value={header.value} placeholder={`Bearer ${secretIn("API_TOKEN")}`} aria-label="Header value" spellCheck={false} onChange={(event) => onChange(replaced(headers, at, { ...header, value: event.target.value }))} />
          <TextAction danger onClick={() => onChange(without(headers, at))}>
            Remove
          </TextAction>
        </div>
      ))}
      <div className="sto-row-foot">
        <TextAction onClick={() => onChange([...headers, aHeader()])}>Add a header</TextAction>
        <span className="sto-hint">
          {secrets.length === 0 ? (
            <>A value may name a secret of this environment, as {secretIn("NAME")}: set one under Agents › Secrets.</>
          ) : (
            <>Secrets you may name: {secrets.map(secretIn).join(", ")}.</>
          )}
        </span>
      </div>
    </div>
  );
}

/** The parameters a tool takes, or the fields a call collects: a name, a type, what it is, and whether it is needed. */
export function ParamRows({ params, adding, onChange }: { params: Param[]; adding: string; onChange: (params: Param[]) => void }): ReactNode {
  return (
    <div className="sto-rows">
      {params.map((param, at) => (
        <div key={at} className="sto-row sto-row-param">
          <Input size="sm" value={param.name} placeholder="name" aria-label="Name" spellCheck={false} onChange={(event) => onChange(replaced(params, at, { ...param, name: event.target.value }))} />
          <Select size="sm" value={param.type} aria-label="Type" onValueChange={(type) => onChange(replaced(params, at, { ...param, type: type as ParamType }))}>
            {PARAM_TYPES.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </Select>
          <Input size="sm" value={param.description} placeholder="What it is, as the model reads it" aria-label="Description" onChange={(event) => onChange(replaced(params, at, { ...param, description: event.target.value }))} />
          <Check checked={param.required} onChange={(required) => onChange(replaced(params, at, { ...param, required }))}>
            Required
          </Check>
          <TextAction danger onClick={() => onChange(without(params, at))}>
            Remove
          </TextAction>
        </div>
      ))}
      <div className="sto-row-foot">
        <TextAction onClick={() => onChange([...params, aParam()])}>{adding}</TextAction>
      </div>
    </div>
  );
}
