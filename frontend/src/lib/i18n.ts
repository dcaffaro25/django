import i18n from "i18next"
import { initReactI18next } from "react-i18next"
import LanguageDetector from "i18next-browser-languagedetector"

import ptBRCommon from "@/locales/pt-BR/common.json"
import ptBRRecon from "@/locales/pt-BR/reconciliation.json"

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "pt-BR",
    supportedLngs: ["pt-BR"],
    defaultNS: "common",
    ns: ["common", "reconciliation"],
    interpolation: { escapeValue: false },
    resources: {
      "pt-BR": {
        common: ptBRCommon,
        reconciliation: ptBRRecon,
      },
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "nord.lang",
      caches: ["localStorage"],
    },
  })

export default i18n
