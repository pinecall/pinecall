/** The editor's Tools: the requests to the business's own API the model may make, a card each, each with its Try box. */

import type { ReactNode } from "react";

import { Button, Field, Input, Select, SelectItem, TextAction, TextArea } from "../../ui";
import type { Definition, HttpTool } from "./door";
import { aTool, LONGEST_TOOL_S, METHODS, toolNameRefused } from "./draft";
import { HeaderRows, ParamRows } from "./rows";
import { Section } from "./section";
import { TryBox } from "./try-box";

export function Tools({
  agent,
  definition,
  secrets,
  onChange,
}: {
  agent: string;
  definition: Definition;
  secrets: readonly string[];
  onChange: (tools: HttpTool[]) => void;
}): ReactNode {
  const tools = definition.tools;
  const replace = (at: number, tool: HttpTool): void => onChange(tools.map((one, index) => (index === at ? tool : one)));
  return (
    <Section
      title="Tools"
      meta="requests to your own API the agent may make during a call"
      action={
        <Button size="sm" onClick={() => onChange([...tools, aTool(tools)])}>
          Add a tool
        </Button>
      }
    >
      {tools.length === 0 && <p className="sto-hint">No tool yet. A tool is one HTTPS request — look up an order, book a slot — whose answer the model reads.</p>}
      {tools.map((tool, at) => (
        <ToolCard
          key={at}
          agent={agent}
          tool={tool}
          definition={definition}
          secrets={secrets}
          onChange={(changed) => replace(at, changed)}
          onRemove={() => onChange(tools.filter((_, index) => index !== at))}
        />
      ))}
    </Section>
  );
}

function ToolCard({
  agent,
  tool,
  definition,
  secrets,
  onChange,
  onRemove,
}: {
  agent: string;
  tool: HttpTool;
  definition: Definition;
  secrets: readonly string[];
  onChange: (tool: HttpTool) => void;
  onRemove: () => void;
}): ReactNode {
  const wrong = toolNameRefused(tool.name);
  return (
    <div className="sto-tool">
      <div className="sto-tool-head">
        <span className="sto-tool-name ui-fixed">{tool.name || "(unnamed)"}</span>
        <TextAction danger onClick={onRemove}>
          Remove
        </TextAction>
      </div>
      <div className="sto-line">
        <Field label="Name" minWidth={180}>
          <Input size="sm" value={tool.name} spellCheck={false} onChange={(event) => onChange({ ...tool, name: event.target.value })} />
        </Field>
        <Field label="Method" minWidth={110}>
          <Select size="sm" value={tool.method} aria-label="Method" onValueChange={(method) => onChange({ ...tool, method: method as HttpTool["method"] })}>
            {METHODS.map((method) => (
              <SelectItem key={method} value={method}>
                {method}
              </SelectItem>
            ))}
          </Select>
        </Field>
        <Field label="URL" grow>
          <Input size="sm" value={tool.url} placeholder="https://api.example.com/orders/{order_id}" spellCheck={false} onChange={(event) => onChange({ ...tool, url: event.target.value })} />
        </Field>
      </div>
      {wrong !== null && <p className="sto-wrong">{wrong}</p>}
      <p className="sto-hint">HTTPS only. A parameter named in the URL as {"{name}"} fills that part of the path; the others go in the query of a GET, or in the JSON body.</p>
      <Field label="What it does, as the model reads it">
        <TextArea value={tool.description} rows={2} placeholder="Looks up an order by its number and answers its status." onChange={(event) => onChange({ ...tool, description: event.target.value })} />
      </Field>
      <div className="sto-label">Parameters</div>
      <ParamRows params={tool.params} adding="Add a parameter" onChange={(params) => onChange({ ...tool, params })} />
      <div className="sto-label">Headers</div>
      <HeaderRows headers={tool.headers} secrets={secrets} onChange={(headers) => onChange({ ...tool, headers })} />
      <div className="sto-line">
        <Field label="Said while it runs (optional)" grow>
          <Input
            size="sm"
            value={tool.announce ?? ""}
            placeholder="One moment, let me check that."
            onChange={(event) => onChange({ ...tool, announce: event.target.value === "" ? null : event.target.value })}
          />
        </Field>
        <Field label={`Wait at most (seconds, up to ${LONGEST_TOOL_S})`} minWidth={200}>
          <Input
            size="sm"
            type="number"
            min={1}
            max={LONGEST_TOOL_S}
            value={String(tool.timeout_s)}
            onChange={(event) => {
              const seconds = event.target.valueAsNumber;
              if (Number.isFinite(seconds)) onChange({ ...tool, timeout_s: seconds });
            }}
          />
        </Field>
      </div>
      <TryBox agent={agent} tool={tool} definition={definition} />
    </div>
  );
}
