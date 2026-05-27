FROM fedora:42

RUN dnf install -y \
    https://download.postgresql.org/pub/repos/yum/reporpms/F-42-x86_64/pgdg-fedora-repo-latest.noarch.rpm && \
    dnf install -y \
    postgresql18-server \
    python3-pip && \
    dnf clean all

RUN pip install patroni[psycopg3,etcd3]

ENV PATH=/usr/pgsql-18/bin:$PATH \
    PGUSER=postgres \
    PGPORT=5432 \
    PGDATABASE=postgres

EXPOSE 5432 8008

USER postgres
WORKDIR /tmp

CMD ["patroni", "/etc/patroni/patroni.yml"]
