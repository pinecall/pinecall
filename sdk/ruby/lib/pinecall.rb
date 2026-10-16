# frozen_string_literal: true

# Pinecall's Ruby SDK: write an agent as a class and serve its calls over the gateway socket.
#
# `Pinecall::Agent` and `Pinecall.mount` are the framework; `Pinecall::Client` is the bare socket
# for applications that decide their own answers.

require "json"
require "pinecall/wire"

require_relative "pinecall/version"
require_relative "pinecall/errors"
require_relative "pinecall/reading"
require_relative "pinecall/view"
require_relative "pinecall/rules"
require_relative "pinecall/blocks"
require_relative "pinecall/panel"
require_relative "pinecall/agent"
require_relative "pinecall/call_world"
require_relative "pinecall/client"
require_relative "pinecall/bridge"
require_relative "pinecall/serve"

module Pinecall
  class << self
    # Mount an agent class on a client; each call gets its own instance. Nothing is sent until
    # `connect`.
    def mount(klass, client:, **options) = Bridge.mount(klass, client:, **options)

    # Render the agent's prompt blocks in send order, offline.
    def render(agent, **context) = Prompt.render(agent, **context)

    # Render the prompt as one page, each block under its header.
    def show_prompt(agent, **context) = Prompt.show(agent, **context)

    # Serve an agent class from inside your own Ruby process: mounted on a client of its own (or
    # the one given), connected, and held. `held.stop` drains then closes, for an `at_exit`.
    def serve(klass, client: nil, url: nil, api_key: nil, env: nil, slug: nil, last: nil)
      client ||= Client.new(url:, api_key:, env:)
      mounted = mount(klass, client:, slug: slug || klass.slug, last:)
      client.connect
      Serve::Held.new(client, [mounted])
    end
  end
end
