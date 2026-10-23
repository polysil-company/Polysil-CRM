# The webhook receiver: Python for hook.py, git and ssh to pull the branch, the
# docker CLI with compose to rebuild through the host's daemon (the socket is
# mounted, which makes this container as powerful as root on the box; it runs
# one fixed script and acts only on a signed push).
FROM docker:27-cli
RUN apk add --no-cache python3 git openssh-client
COPY hook.py redeploy.sh Dockerfile docker-compose.frontend.yml /opt/hook/
RUN chmod 755 /opt/hook/redeploy.sh
EXPOSE 9000
CMD ["python3", "-u", "/opt/hook/hook.py"]
