# frozen_string_literal: true

module Pinecall
  class Client
    # Reads a log as a JSON page or an SSE stream, reduced by the wire's reducer.
    #
    # Reconnects resume with `Last-Event-ID`. A reader that fell behind gets `log.gap` (with a
    # snapshot when available), then `log.caught_up` once the stream is live.
    module Observe
      # One page of entries after the cursor, their reduced state, and the next cursor.
      Page = Data.define(:entries, :state, :live, :next)

      # One entry, its decoded event, and the reduced state including it.
      Observation = Data.define(:entry, :event, :state)

      RETRY_S = 1.0
      LONGEST_RETRY_S = 30.0

      module_function

      # Fetch one page after `after`. Use the page's `next`, not the last entry's seq: an empty
      # page of a live log still has one.
      def history(target, url:, api_key:, after: 0)
        answer = get(target, url:, api_key:, after:, accept: "application/json")
        page = JSON.parse(answer.body, symbolize_names: true)
        raise Error, "the log page is not { entries, live, next }" unless page.is_a?(Hash) && page[:entries].is_a?(Array)

        entries = page[:entries].map { |raw| Wire.decode_entry(raw) }
        Page.new(entries:, state: Wire.reduce(entries), live: page[:live] == true,
                 next: page[:next].is_a?(Integer) ? page[:next] : nil)
      end

      # Stream entries after `after`, reconnecting as needed. Yields an Observation per entry;
      # returns when the block breaks or `stop` returns true.
      def observe(target, url:, api_key:, after: 0, stop: nil)
        state = Wire.initial_state
        attempt = 0
        opened = false
        until stop&.call
          begin
            stream(target, url:, api_key:, after:) do |entry|
              attempt = 0
              opened = true
              after = entry.seq
              state = Wire.apply(state, entry)
              yield Observation.new(entry:, event: Wire.event_of(entry), state:)
            end
          rescue StandardError
            # Failing before the first entry means misconfiguration: raise. Later drops resume.
            raise unless opened
          end
          attempt += 1
          sleep([LONGEST_RETRY_S, RETRY_S * (2**(attempt - 1))].min * rand)
        end
      end

      def stream(target, url:, api_key:, after:)
        get(target, url:, api_key:, after:, accept: "text/event-stream") do |answer|
          buffered = +""
          answer.read_body do |chunk|
            buffered << chunk
            while (cut = buffered.index("\n\n"))
              block = buffered.slice!(0, cut + 2)
              entry = entry_in(block)
              yield entry unless entry.nil?
            end
          end
        end
      end

      # Parse one SSE block; nil for comments and keep-alives.
      def entry_in(block)
        data = block.lines.filter_map { |line| line.delete_prefix("data:").lstrip.chomp if line.start_with?("data:") }
        return nil if data.empty?

        Wire.decode_entry(JSON.parse(data.join("\n"), symbolize_names: true))
      end

      def get(target, url:, api_key:, after:, accept:, &block)
        where = URI.parse(door(target, url))
        where.query = URI.encode_www_form(after:) if after.positive?
        request = Net::HTTP::Get.new(where)
        request["accept"] = accept
        request["authorization"] = "Bearer #{api_key}"
        request["last-event-id"] = after.to_s if after.positive?
        answer(where, request, &block)
      end

      def answer(where, request)
        http = Net::HTTP.new(where.host, where.port)
        http.use_ssl = where.scheme == "https"
        http.read_timeout = nil
        http.start do |open|
          open.request(request) do |response|
            raise Error, "#{where.path}: the gateway answered #{response.code}" unless response.is_a?(Net::HTTPSuccess)

            return block_given? ? yield(response) : response.tap(&:body)
          end
        end
      end

      def door(target, url)
        return Endpoints.call_log(url, target[:call]) if target[:call]

        Endpoints.agent_log(url, target.fetch(:agent))
      end
    end
  end
end
