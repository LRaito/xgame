import pluginVue from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";

export default [
    {
        ignores: ["dist/**", "node_modules/**", "public/**"],
    },
    ...pluginVue.configs["flat/recommended"],
    {
        files: ["**/*.vue", "**/*.js"],
        ignores: ["dist/**", "node_modules/**", "public/**"],
        languageOptions: {
            parser: vueParser,
            ecmaVersion: 2022,
            sourceType: "module",
        },
        rules: {
            "vue/multi-word-component-names": "off",
            "vue/max-attributes-per-line": "off",
            "vue/singleline-html-element-content-newline": "off",
            "vue/html-self-closing": "off",
            "vue/html-indent": ["error", 4],
            "vue/script-indent": ["error", 4],
        },
    },
];
