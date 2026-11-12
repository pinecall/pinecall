# frozen_string_literal: true

module Pinecall
  module Serve
    # The app's page on this machine: its folder, its config, and the visitor's ticket passed on.
    class Paged
      # The port the page is served on unless `PINECALL_PAGE_PORT` names another.
      PORT = 4747
      INDEX = "index.html"
      NOT_BUILT = "the page is not built yet: build it into the folder app.page names, and reload"
      TYPES = { ".html" => "text/html; charset=utf-8", ".js" => "text/javascript", ".mjs" => "text/javascript",
                ".css" => "text/css", ".json" => "application/json", ".svg" => "image/svg+xml", ".png" => "image/png",
                ".jpg" => "image/jpeg", ".webp" => "image/webp", ".ico" => "image/x-icon", ".woff2" => "font/woff2" }.freeze

      # One answer: its status, its body and what the body is.
      Said = Data.define(:status, :body, :type)

      def initialize(folder:, agent:, url:, api_key:, env:, port:)
        @folder = File.expand_path(folder)
        @agent = agent
        @url = url
        @api_key = api_key
        @env = env
        @port = port
      end

      # Serve on a thread of its own until `stop`; raises when the port is taken.
      def start
        @server = TCPServer.new("127.0.0.1", @port)
        @thread = Thread.new { loop { Thread.new(@server.accept) { |client| answer(client) } } }
        self
      end

      def stop
        @thread&.kill
        @server&.close
      end

      # A GET: the page's config, or a file of the built folder.
      def got(path)
        # No captcha here: the key is the developer's own, and nobody else reaches the port.
        return Said.new(200, JSON.generate({ agent: @agent, turnstile: nil }), "application/json") if path == "/pinecall/config"

        file_of(path)
      end

      # A POST: a visitor's ticket or code, asked of the gateway with the key.
      def posted(path, body)
        asked = begin
          JSON.parse(body.to_s.empty? ? "{}" : body, symbolize_names: true)
        rescue JSON::ParserError
          {}
        end
        case path
        when "/pinecall/token"
          passed("/v1/tokens", { agent: @agent, scope: asked[:scope] == "chat" ? "chat" : "talk", resume: asked[:resume] }.compact)
        when "/pinecall/code" then passed("/v1/codes", { agent: @agent })
        else Said.new(405, JSON.generate({ detail: "a page is read" }), "application/json")
        end
      end

      # A path that names no file is the page itself, so its own router reads it.
      def file_of(path)
        asked = File.expand_path(File.join(@folder, URI.decode_www_form_component(path)))
        inside = asked == @folder || asked.start_with?("#{@folder}/")
        found = inside && File.file?(asked) ? asked : File.join(@folder, INDEX)
        if !inside || (found != asked && !File.extname(path).empty?) || !File.file?(found)
          gone = File.file?(File.join(@folder, INDEX)) ? "the page has no file #{path}" : NOT_BUILT
          return Said.new(404, JSON.generate({ detail: gone }), "application/json")
        end
        Said.new(200, File.binread(found), TYPES.fetch(File.extname(found), "application/octet-stream"))
      end

      private

      def passed(door, body)
        request = Net::HTTP::Post.new(URI.parse("#{@url.chomp("/")}#{door}"))
        request["content-type"] = "application/json"
        request["authorization"] = "Bearer #{@api_key}"
        request[Client::Rest::ENV_HEADER] = @env unless @env.nil?
        request.body = JSON.generate(body)
        where = request.uri
        http = Net::HTTP.new(where.host, where.port)
        http.use_ssl = where.scheme == "https"
        answered = http.request(request)
        Said.new(answered.code.to_i, answered.body.to_s, "application/json")
      rescue SystemCallError, IOError, Timeout::Error => e
        Said.new(502, JSON.generate({ detail: e.message }), "application/json")
      end

      def answer(client)
        method, target = client.gets.to_s.split
        headers = {}
        while (line = client.gets) && line != "\r\n"
          name, value = line.split(":", 2)
          headers[name.downcase] = value.to_s.strip
        end
        path = URI.parse(target.to_s).path
        said = method == "POST" ? posted(path, client.read(headers["content-length"].to_i)) : got(path)
        client.write("HTTP/1.1 #{said.status} OK\r\ncontent-type: #{said.type}\r\ncache-control: no-store\r\n" \
                     "content-length: #{said.body.bytesize}\r\nconnection: close\r\n\r\n")
        client.write(said.body)
      rescue StandardError
        nil
      ensure
        client.close
      end
    end
  end
end
