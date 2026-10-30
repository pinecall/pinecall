# frozen_string_literal: true

module Pinecall
  module Serve
    # The folder a class declares as its base, pushed once the agent registers: `docs/` beside the
    # class, every Markdown file under it, by path, the base's other files kept. Nothing for a class
    # that declares no base, a folder that is not there, or one with no Markdown in it.
    module DeclaredDocs
      DOCS_FOLDER = "docs"

      module_function

      # Every Markdown file under the folder, its path as the base keeps it; none for no folder.
      def markdown_under(folder)
        return [] unless File.directory?(folder)

        Dir.glob("**/*.md", base: folder).sort.map do |path|
          { path:, text: File.read(File.join(folder, path), encoding: "utf-8") }
        end
      end

      # Push the class's folder into the base it declares, and say what landed on `err`; `put` is
      # the request, the REST door's unless a test hands another.
      def push(client, klass, file, err:, put: Client::Rest.method(:put))
        base = klass.environment.dig(:docs, :base)
        return if base.nil? || file.nil?

        files = markdown_under(File.join(File.dirname(File.expand_path(file)), DOCS_FOLDER))
        return if files.empty?

        url = "#{client.url.sub(%r{/\z}, "")}/v1/knowledge/#{URI.encode_www_form_component(base.to_s)}"
        pushed = put.call(url, { files: }, api_key: client.api_key, env: client.env) || {}
        kept = pushed[:kept].to_i
        line = "#{klass.slug}  #{base}  #{files.size} file(s) pushed · #{pushed[:chunks].to_i} chunk(s)"
        err.puts(kept.positive? ? "#{line} · #{kept} kept" : line)
      end
    end
  end
end
