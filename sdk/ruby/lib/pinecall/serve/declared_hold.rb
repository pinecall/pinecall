# frozen_string_literal: true

require "digest"

module Pinecall
  module Serve
    # The melody a class ships, uploaded once the agent registers unless the gateway holds that file:
    # the door keeps the hash of what was uploaded, so a second start with the same file sends nothing.
    module DeclaredHold
      module_function

      def upload(client, klass, file, err:, get: Client::Rest.method(:get), put: Client::Rest.method(:put_bytes))
        declared = klass.hold
        return unless declared.is_a?(Hash) && !declared[:file].nil?

        path, data = Agent::Melody.melody_of(declared, file)
        sha256 = Digest::SHA256.hexdigest(data)
        door = "#{client.url.sub(%r{/\z}, "")}/v1/agents/#{URI.encode_www_form_component(klass.slug)}/hold-audio"
        held = get.call(door, api_key: client.api_key, env: client.env) || {}
        return if held[:source_sha256] == sha256

        landed = put.call("#{door}?name=#{URI.encode_www_form_component(File.basename(path))}", data, api_key: client.api_key, env: client.env) || {}
        err.puts("#{klass.slug}  #{File.basename(path)} uploaded as the hold melody · #{landed[:seconds] || "?"} s")
      end
    end
  end
end
