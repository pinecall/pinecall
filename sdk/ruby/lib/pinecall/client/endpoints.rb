# frozen_string_literal: true

module Pinecall
  class Client
    # Gateway URLs built from the configured base URL.
    module Endpoints
      module_function

      # `WS /v1/apps`; an http(s) base is converted to ws(s).
      def apps(base) = door(base, "/v1/apps", websocket: true)

      # `GET /v1/calls/{id}/events`: a call's log, as JSON or SSE.
      def call_log(base, call) = door(base, "/v1/calls/#{CGI.escape(call)}/events")

      # `GET /v1/agents/{slug}/calls`: the agent's log (registrations, configs, errors).
      def agent_log(base, agent) = door(base, "/v1/agents/#{CGI.escape(agent)}/calls")

      # `POST /v1/calls/{id}/lookup`: a platform tool run for one call this app serves.
      def lookup(base, call) = door(base, "/v1/calls/#{CGI.escape(call)}/lookup")

      def door(base, path, websocket: false)
        url = URI.parse(base)
        secure = %w[https wss].include?(url.scheme)
        url.scheme = websocket ? (secure ? "wss" : "ws") : (secure ? "https" : "http")
        url.path = "#{url.path.chomp("/")}#{path}"
        url.to_s
      end
    end
  end
end
