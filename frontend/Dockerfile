# 基础镜像固定到具体补丁版本 + 发行版代号（不用 node:22-alpine 这类浮动标签）：
# 浮动标签会在上游重发时悄悄换掉 Node 版本与 Alpine 基线，构建产物跟着变、还难排查。
# 升级请手动改这一行。
FROM node:22.23.3-alpine3.24 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# 版本号由 make build 经 docker-compose 的 web.build.args 注入（仓库根的 Makefile 能读到 .git，
# 构建上下文里没有）。直接 docker compose build 时为空串，由 vite.config.js 用时间戳兜底。
ARG APP_VERSION=""
# 显式在命令里引用 $APP_VERSION：让 ARG 值进入本层缓存键，改了 sha 就一定重建。
# dist/version.txt 由 vite 插件写出，与注入 bundle 的是同一个值；
# test -s 保证插件一旦失效构建就失败，而不是部署一个永远探测不到版本的产物。
RUN APP_VERSION="$APP_VERSION" npm run build && test -s dist/version.txt

# 同上：nginx 也固定补丁版本 + Alpine 代号（nginx:1.27-alpine 会随上游重发漂移）。
FROM nginx:1.27.5-alpine3.21
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
