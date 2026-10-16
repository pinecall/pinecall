# frozen_string_literal: true

module Pinecall
  class Client
    # Authenticated JSON requests to the gateway's REST endpoints. Non-2xx responses raise
    # `Refused` with the gateway's message, never a bare status.
    module Rest
      # The header naming the world a request or a socket acts in.
      ENV_HEADER = "pinecall-env"

      module_function

      def get(url, api_key:, env: nil) = ask(Net::HTTP::Get.new(URI.parse(url)), api_key:, env:)

      def put(url, body, api_key:, env: nil)
        request = Net::HTTP::Put.new(URI.parse(url))
        request["content-type"] = "application/json"
        request.body = JSON.generate(body)
        ask(request, api_key:, env:)
      end

      def post(url, body, api_key:, env: nil)
        request = Net::HTTP::Post.new(URI.parse(url))
        request["content-type"] = "application/json"
        request.body = JSON.generate(body)
        ask(request, api_key:, env:)
      end

      def delete(url, api_key:, env: nil) = ask(Net::HTTP::Delete.new(URI.parse(url)), api_key:, env:)

      # Returns the body with symbol keys (nil if empty); raises `Refused` on failure. `env` names
      # the world the request acts in (`pinecall-env`); a server's token needs none.
      def ask(request, api_key:, env: nil)
        request["authorization"] = "Bearer #{api_key}"
        request[ENV_HEADER] = env unless env.nil?
        request["accept"] = "application/json"
        where = request.uri
        http = Net::HTTP.new(where.host, where.port)
        http.use_ssl = where.scheme == "https"
        answer = http.request(request)
        body = parsed(answer.body)
        return body if answer.is_a?(Net::HTTPSuccess)

        raise Refused.new({ code: answer.code, message: sentence(body, answer) })
      end

      def parsed(text)
        return nil if text.nil? || text.strip.empty?

        JSON.parse(text, symbolize_names: true)
      rescue JSON::ParserError
        nil
      end

      # Gateway refusals use `detail`; otherwise pass the body through.
      def sentence(body, answer)
        (body.is_a?(Hash) && (body[:detail] || body[:message])) || answer.body.to_s.strip
      end
    end
  end
end
