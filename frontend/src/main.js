import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus, { ElDialog } from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";

import App from "./App.vue";
import router from "./router";
import { ensureCsrf } from "./utils/request";
import AppButton from "@components/common/AppButton.vue";
import AppEmpty from "@components/common/AppEmpty.vue";
import CopyButton from "@components/common/CopyButton.vue";
import "./styles/index.css";
import "./permission";
import { ensureGameAssetSw } from "./utils/gameAssetCache";
import { startVersionCheck } from "./utils/versionCheck";

ElDialog.props.closeOnClickModal.default = false;

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(ElementPlus, { locale: zhCn });
app.component("AppButton", AppButton);
app.component("AppEmpty", AppEmpty);
app.component("CopyButton", CopyButton);

ensureCsrf().catch(() => {});
ensureGameAssetSw().catch(() => {});
// 探测服务端是否已部署新版本（dev 下自动跳过），见 utils/versionCheck.js
startVersionCheck();
app.mount("#app");
