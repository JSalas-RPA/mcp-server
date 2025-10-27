FROM denoland/deno:alpine-1.37.2

WORKDIR /app
COPY server.ts .
RUN deno cache server.ts
EXPOSE 7000
CMD ["run", "--allow-net", "server.ts"]
