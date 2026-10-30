# frozen_string_literal: true

require "digest"

module Pinecall
  class Agent
    # The hold melody a class declares: `hold file: "hold.mp3", after_s: 1.5`, `hold after_s: 1`,
    # `hold off: true` or `hold :off`. The file is read beside the class and named on the wire by its
    # sha256; the serve entry ships it once the agent registers.
    module Melody
      NOT_A_HOLD = "hold is the melody: hold file: \"hold.mp3\", after_s: 1.5; hold after_s: …; hold off: true; or hold :off"
      NO_SUCH_FILE = "hold names %s, and there is no such file beside the class"

      module_function

      # What the class declares, as the wire carries it: the file by hash, the wait, silence; nil for none.
      def config_of(declared, source_file)
        return nil if declared.nil?
        return { off: true } if declared == :off || declared == "off"
        raise DeclarationRefused, NOT_A_HOLD unless declared.is_a?(Hash)

        hold = {}
        hold[:after_s] = declared[:after_s] unless declared[:after_s].nil?
        hold[:off] = true if declared[:off] == true
        unless declared[:file].nil?
          path, data = melody_of(declared, source_file)
          hold[:clip] = Digest::SHA256.hexdigest(data)
          hold[:name] = File.basename(path)
        end
        hold
      end

      # The file the class ships as its melody, read beside the class's own file: its path and its bytes.
      def melody_of(declared, source_file)
        named = declared[:file]
        raise DeclarationRefused, NOT_A_HOLD unless named.is_a?(String) && !named.empty?

        path = source_file.nil? ? File.expand_path(named) : File.expand_path(named, File.dirname(source_file))
        raise DeclarationRefused, format(NO_SUCH_FILE, path) unless File.file?(path)

        [path, File.binread(path)]
      end
    end
  end
end
