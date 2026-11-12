# frozen_string_literal: true

module Pinecall
  class Client
    # A voice app's side of its flows: the events and the runs the gateway keeps for it, over HTTP.
    module AppWork
      # The gateway, the key and the app the work is asked for.
      Door = Data.define(:url, :api_key, :env, :app)

      module_function

      # What the app is owed, waited for up to `wait_s` seconds: `{ events: [...], runs: [...] }`.
      def take_work(door, wait_s) = asked(door, :post, "/work", { wait_s: }) || { events: [], runs: [] }

      # The event was handled.
      def event_heard(door, event) = asked(door, :post, "/events/#{event}/heard", {})

      # Start a flow with an input; the same key is the same run.
      def start_run(door, flow, key, input) = asked(door, :post, "/runs", { flow:, key:, input: })

      # Write the run's next step, and read the run as it stands after it.
      def write_step(door, run, step) = asked(door, :post, "/runs/#{escaped(run)}/steps", step)

      # One run with its journal.
      def read_run(door, run) = asked(door, :get, "/runs/#{escaped(run)}")

      # The app's runs of one flow in one status, newest first.
      def runs_of(door, flow, status)
        (asked(door, :get, "/runs?flow=#{escaped(flow)}&status=#{escaped(status)}") || {})[:runs] || []
      end

      # The flow returned or raised.
      def end_run(door, run, status, error = nil) = asked(door, :post, "/runs/#{escaped(run)}/end", { status:, error: }.compact)

      # Stop a run where it stands.
      def cancel_run(door, run) = asked(door, :post, "/runs/#{escaped(run)}/cancel", {})

      # Have a live call run on `agent`'s model and voice from here on; the gateway's status.
      def staged_as(door, call, agent)
        request = Net::HTTP::Post.new(URI.parse("#{door.url.chomp("/")}/v1/calls/#{escaped(call)}/stages"))
        request["content-type"] = "application/json"
        request["authorization"] = "Bearer #{door.api_key}"
        request[Rest::ENV_HEADER] = door.env unless door.env.nil?
        request.body = JSON.generate({ agent: })
        where = request.uri
        http = Net::HTTP.new(where.host, where.port)
        http.use_ssl = where.scheme == "https"
        http.request(request).code.to_i
      end

      def asked(door, method, path, body = nil)
        url = "#{door.url.chomp("/")}/v1/apps/#{escaped(door.app)}#{path}"
        return Rest.get(url, api_key: door.api_key, env: door.env) if method == :get

        Rest.post(url, body, api_key: door.api_key, env: door.env)
      end

      def escaped(part) = URI.encode_www_form_component(part.to_s)
    end
  end
end
