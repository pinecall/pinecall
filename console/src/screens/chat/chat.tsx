/** Chat: the class of this directory talked to in writing, in the browser, on the call's own log. */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Button, Field, Input, Refused, Select, SelectItem } from "../../ui";
import { Inspector } from "../talk/inspector";
import { useWatchedCall } from "../call/use-watched-call";
import { Bubbles, type Pending } from "./bubbles";
import { endChat, readChatRoster, sayInChat, startChat, type Roster } from "./door";
import "./chat.css";

/**
 * The screen. It asks the process that holds the agent, never the gateway's model: a written call
 * is served by the class mounted where `pinecall start` was typed, exactly as `pinecall chat` serves
 * one — so a breakpoint in a @tool is reachable in that terminal. The call in the path is the call
 * being talked to, so a reload lands back in the same conversation.
 */
export function Chat(): ReactNode {
  const params = useParams();
  const agent = params["agent"] ?? "";
  const call = params["call"];
  return (
    <div className="chat-grid">
      <div className="chat-column">
        {call === undefined ? <Opening agent={agent} /> : <Conversation agent={agent} call={call} />}
      </div>
      <Inspector agent={agent} call={call ?? null} />
    </div>
  );
}

function ChatHead({ agent, children }: { agent: string; children?: ReactNode }): ReactNode {
  return (
    <div className="chat-head">
      <div className="chat-head-words">
        <div className="chat-title">Chat with {agent}</div>
        <div className="chat-sub">The same agent, typed instead of spoken — every turn still lands in the log.</div>
      </div>
      {children}
    </div>
  );
}

/** Before a conversation: who is writing, and the state it may open in. */
function Opening({ agent }: { agent: string }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [roster, setRoster] = useState<Roster | null>(null);
  const [as, setAs] = useState("");
  const [golden, setGolden] = useState("");
  const [refused, setRefused] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    let gone = false;
    readChatRoster(credentials, agent).then(
      (read) => {
        if (!gone) setRoster(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  const open = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setOpening(true);
    setRefused(null);
    try {
      void navigate(`/a/${agent}/dev-chat/${await startChat(credentials, agent, as.trim(), golden)}`);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setOpening(false);
    }
  };

  return (
    <>
      <ChatHead agent={agent} />
      <div className="chat-lines">
        <div className="chat-start ui-card">
          <div className="ui-card-head">
            <span className="ui-card-title">Start a conversation</span>
          </div>
          <div className="ui-card-body">
            {roster === null && refused === null && <p className="chat-note">Asking the terminal that holds {agent}…</p>}
            {roster !== null && roster.agent !== agent && (
              <p className="chat-note">
                {roster.agent === null
                  ? "No agent class in the directory this agent's `pinecall start` runs in, so there is nothing to chat with. Run `pinecall start` where its agent.tsx is."
                  : `The process holding the agent runs in ${roster.agent}'s directory: to chat with ${agent}, run \`pinecall start\` there.`}
              </p>
            )}
            {roster !== null && roster.agent === agent && (
              <form className="chat-start-form" onSubmit={(event) => void open(event)}>
                <p className="chat-note">
                  The class of this directory, in writing. Its tools run in the terminal that serves this page, and a conversation can
                  open part-way through, in the state one of the goldens declares.
                </p>
                <Field label="As">
                  <Input value={as} placeholder="a phone number, a customer id — or nobody" onChange={(event) => setAs(event.target.value)} />
                </Field>
                {roster.states.length > 0 && (
                  <Field label="From">
                    <Select value={golden} onValueChange={(value) => setGolden(value)}>
                      <SelectItem value="">the call's own opening</SelectItem>
                      {roster.states.map((name) => (
                        <SelectItem key={name} value={name}>
                          the state of {name}
                        </SelectItem>
                      ))}
                    </Select>
                  </Field>
                )}
                <div>
                  <Button kind="primary" size="form" type="submit" disabled={opening}>
                    {opening ? "Opening…" : "Start the chat"}
                  </Button>
                </div>
              </form>
            )}
            <Refused>{refused}</Refused>
          </div>
        </div>
      </div>
    </>
  );
}

/** The bubbles and the composer together: a line you send is on screen before the log confirms it. */
function Conversation({ agent, call }: { agent: string; call: string }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [pending, setPending] = useState<Pending[]>([]);
  const [refused, setRefused] = useState<string | null>(null);
  const next = useRef(0);
  const watched = useWatchedCall(call);
  // A chat opened from its link after it ended is a transcript: nothing to hang up, nobody to say it to.
  const over = watched.state.status === "ended" || watched.connection === "ended";

  // Hanging up is what seals the log and runs the judges at ring 4, so it is a button and not a
  // navigation: leaving the page would keep the socket open in the terminal behind it.
  const hangUp = async (): Promise<void> => {
    try {
      await endChat(credentials, agent, call);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      return;
    }
    void navigate(`/calls/${call}`);
  };

  return (
    <>
      <ChatHead agent={agent}>
        <div className="chat-head-actions">
          <Link className="chat-whole" to={`/calls/${call}`}>
            Open ↗
          </Link>
          {!over && (
            <Button size="md" onClick={() => void hangUp()} title="hanging up seals the log and runs the judges">
              Hang up
            </Button>
          )}
        </div>
      </ChatHead>
      <Bubbles
        watched={watched}
        pending={pending}
        onConfirmed={(text) =>
          setPending((now) => {
            const at = now.findIndex((line) => line.text === text);
            return at === -1 ? now : [...now.slice(0, at), ...now.slice(at + 1)];
          })
        }
      />
      {refused !== null && (
        <div className="chat-refused">
          <Refused>{refused}</Refused>
        </div>
      )}
      {over ? (
        <div className="chat-over">This chat has ended — its own page has it whole.</div>
      ) : (
      <Composer
        agent={agent}
        call={call}
        onRefused={setRefused}
        onSent={(text) => {
          next.current += 1;
          const line = { id: next.current, text };
          setPending((now) => [...now, line]);
          return () => setPending((now) => now.filter((one) => one.id !== line.id));
        }}
      />
      )}
    </>
  );
}

/** The caller's side: one line at a time down the socket the terminal holds. */
function Composer({
  agent,
  call,
  onSent,
  onRefused,
}: {
  agent: string;
  call: string;
  onSent: (text: string) => () => void;
  onRefused: (refused: string | null) => void;
}): ReactNode {
  const credentials = useCredentials();
  const [text, setText] = useState("");

  // The line leaves the box at once and stands greyed in the conversation; the log's turn.user
  // settles it. A refusal takes it back and puts the words in the box again.
  const say = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const said = text.trim();
    if (said === "") return;
    setText("");
    onRefused(null);
    const takeBack = onSent(said);
    try {
      await sayInChat(credentials, agent, call, said);
    } catch (failed) {
      takeBack();
      setText(said);
      onRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  return (
    <form className="chat-composer" onSubmit={(event) => void say(event)}>
      <input className="chat-say" value={text} autoFocus placeholder="Ask the agent something" onChange={(event) => setText(event.target.value)} />
      <button type="submit" className="chat-send" disabled={text.trim() === ""}>
        Send
      </button>
    </form>
  );
}
