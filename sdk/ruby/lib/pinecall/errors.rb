# frozen_string_literal: true

module Pinecall
  # Base class for every error raised by this library. Messages say what went wrong and how to
  # fix it.
  class Error < StandardError
  end

  # The gateway refused a command with an `error` entry.
  class Refused < Error
    # @return [Hash{Symbol=>Object}] the wire refusal: code, message and id
    attr_reader :refusal

    def initialize(refusal)
      @refusal = refusal
      super("#{refusal[:code]}: #{refusal[:message]}")
    end

    # Machine-readable refusal code.
    def code = @refusal[:code]
  end

  # A state field was assigned outside a tool or hook.
  class UnauthoredWrite < Error
    def initialize(field)
      super("state field #{field} was assigned outside a tool and outside a lifecycle hook; " \
            "tools are the only writers of state")
    end
  end

  # A declaration the gateway would refuse, raised at load.
  class DeclarationRefused < Error
  end

  # A console's ask refused with a status: raised by an `on_dev` handler, answered as `refused`.
  class DevRefused < Error
    attr_reader :status, :detail

    def initialize(status, detail)
      @status = status
      @detail = detail
      super("#{status}: #{detail}")
    end
  end

  # A tool failed; the message is returned to the model as the tool result.
  class ToolFailed < Error
  end

  # The socket is not connected.
  class NotConnected < Error
  end
end
