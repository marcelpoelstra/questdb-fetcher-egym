FROM python:3.14.7-alpine3.24 AS build
RUN apk add git
RUN python -m venv /opt/venv
COPY pyproject.toml /src/
COPY questdb_fetcher_egym /src/questdb_fetcher_egym
RUN /opt/venv/bin/pip install /src

FROM python:3.14.7-alpine3.24
RUN apk add tini && adduser -D fetcher
COPY --from=build /opt/venv /opt/venv
USER fetcher
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/opt/venv/bin/python", "-m", "questdb_fetcher_egym"]
