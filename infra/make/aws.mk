# AWS's side of the runtime's Makefile (PROVIDER = aws in the operator's <cluster>.mk): who
# Terraform acts as, where the cluster and its registry are, how an image is built and found, where
# the hosted apps run. The operator's <cluster>.mk gives ACCOUNT (the account's twelve digits), and
# REGION or CONTEXT where they are not these. What a provider's file must define is the list in
# infra/README.md, "Another cloud".

REGION   ?= us-east-1
# The context `aws eks update-kubeconfig --name pinecall-<name> --region <region>` writes.
CONTEXT  ?= arn:aws:eks:$(REGION):$(ACCOUNT):cluster/pinecall-$(NAME)

# AWS's credentials are the operator's own login (~/.aws, or the environment's), read by Terraform
# itself: nothing is handed over but the region.
TF_AUTH   = AWS_REGION=$(REGION)
# The account's root (ROOT=project) among the operator's files: aws-project.tfvars and
# aws-project.backend.hcl, so an operator with clusters on two clouds keeps both.
TF_PROJECT ?= aws-project

# The images: Elastic Container Registry, a repository an image (terraform/aws/project), built by
# CodeBuild as the builds' own role, never on the laptop.
REGISTRY ?= $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/pinecall
# $(call build,<the context: a folder or a .tar.gz>,<runtime|mcp|plain>,<image>:<tag>)
build     = REGION=$(REGION) ACCOUNT=$(ACCOUNT) $(INFRA)/make/aws-build $(1) $(2) $(3)
# $(call digest,<image>:<tag>): what the registry holds for it (`sha256:…`), or nothing.
digest    = $$(REGION=$(REGION) $(INFRA)/make/aws-digest $(1))

# $(call on,<a machine of a server>,<user>,<script>,<arguments>): a script of this repository run
# on that machine, in a session of Systems Manager as the operator's own login.
on        = REGION=$(REGION) $(INFRA)/make/aws-on $(1) $(2) $(3) $(4)

# The hosted apps run on a fenced pool of the cluster itself (terraform/aws/modules/hosting): the
# same context, and no credentials to fetch.
HOSTING  ?= $(CONTEXT)
hosting_credentials = @:
