# Add only a static readiness probe to the official, pinned distroless image.
ARG PROBE_IMAGE=busybox:1.37.0-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092
FROM ${PROBE_IMAGE} AS probe
FROM grafana/loki:3.6.18@sha256:700eaaa9fbd4275914d6b11f77c080b5ba0b983f6690055e48264ea77cb0bf6f
COPY --from=probe /bin/busybox /bin/busybox
USER 10001:10001
HEALTHCHECK --interval=10s --timeout=3s --start-period=45s --retries=12 CMD ["/bin/busybox", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:3100/ready"]
