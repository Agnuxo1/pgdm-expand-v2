# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: Apache-2.0
# Research-Project: pgdm-expand-v2
# Research-Date: 2026-11-04
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Attribution-Recorded-On: 2026-11-06
# Reuse: preserve upstream Apache-2.0 notices and cite the author of original changes.
# Reproducible bench: PostgreSQL 16 + OpenSSH + Python for the headless DB Manager.
# The official Manager runs on Windows and connects over SSH; here the harness connects over
# SSH to 127.0.0.1 inside the container (SSH transit is excluded from the official metric).
FROM postgres:16-alpine
RUN apk add --no-cache openssh-server python3 py3-paramiko py3-pandas py3-psutil bash coreutils procps util-linux \
 && ssh-keygen -A \
 && adduser -D -s /bin/bash pdm \
 && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?MaxSessions.*/MaxSessions 64/' /etc/ssh/sshd_config \
 && echo 'MaxStartups 64:30:128' >> /etc/ssh/sshd_config
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh
ENTRYPOINT ["/entry.sh"]
