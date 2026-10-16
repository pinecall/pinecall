# frozen_string_literal: true

module Pinecall
  class Client
    # Event listener registry, used per agent and per call. A raising listener is reported to
    # `on_error` and the remaining listeners still run.
    class Listeners
      def initialize(&on_error)
        @by_type = Hash.new { |kept, type| kept[type] = [] }
        @any = []
        @on_error = on_error
        @lock = Mutex.new
      end

      # Listen for one event type; the returned lambda unsubscribes.
      def on(type, &listener)
        @lock.synchronize { @by_type[type.to_s] << listener }
        -> { @lock.synchronize { @by_type[type.to_s].delete(listener) } }
      end

      def on_any(&listener)
        @lock.synchronize { @any << listener }
        -> { @lock.synchronize { @any.delete(listener) } }
      end

      # Notify type listeners, then catch-all listeners.
      def emit(event, context)
        for_type, for_any = @lock.synchronize { [@by_type[event.type].dup, @any.dup] }
        for_type.each { |listener| run { listener.call(event.data, context) } }
        for_any.each { |listener| run { listener.call(event, context) } }
      end

      private

      def run
        yield
      rescue StandardError => e
        @on_error.call(e)
      end
    end
  end
end
