# frozen_string_literal: true

# The one error of the wire: a frame, an entry or a body that does not fit its shape.

module Pinecall
  module Wire
    # A message did not match the protocol: an unknown type, a bad shape, an undeclared key.
    # Raised where the frame is built or received, so the backtrace points at the caller.
    class WireError < StandardError
    end
  end
end
