import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "out/**"]
  },
  ...nextVitals
];

export default eslintConfig;
