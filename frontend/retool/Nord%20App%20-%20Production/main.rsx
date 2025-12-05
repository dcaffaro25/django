<App>
  <Include src="./functions.rsx" />
  <Include src="./src/home.rsx" />
  <Include src="./src/cadastroContabilidade.rsx" />
  <Include src="./src/bankReconciliation.rsx" />
  <Include src="./src/page3.rsx" />
  <Include src="./src/configuracoes.rsx" />
  <Include src="./src/Transacoes.rsx" />
  <CustomAppTheme
    id="$appTheme"
    _migrated={true}
    automatic={[
      "#fde68a",
      "#eecff3",
      "#a7f3d0",
      "#bfdbfe",
      "#c7d2fe",
      "#fecaca",
      "#fcd6bb",
    ]}
    borderRadius="4px"
    canvas="#f6f6f6"
    danger="#dc2626"
    defaultFont={{ size: "12px", fontWeight: "400" }}
    h1Font={{ size: "36px", fontWeight: "700" }}
    h2Font={{ size: "28px", fontWeight: "700" }}
    h3Font={{ size: "24px", fontWeight: "700" }}
    h4Font={{ size: "18px", fontWeight: "700" }}
    h5Font={{ size: "16px", fontWeight: "700" }}
    h6Font={{ size: "14px", fontWeight: "700" }}
    highlight="#fde68a"
    info="#3170f9"
    labelEmphasizedFont={{ size: "12px", fontWeight: "600" }}
    labelFont={{ size: "12px", fontWeight: "500" }}
    primary="#025736"
    secondary="#025736"
    success="#059669"
    surfacePrimary="#ffffff"
    surfacePrimaryBorder=""
    surfaceSecondary="#ffffff"
    surfaceSecondaryBorder=""
    tertiary="#000000"
    textDark="#0d0d0d"
    textLight="#ffffff"
    warning="#cd6f00"
  />
  <AppStyles id="$appStyles" css={include("./lib/$appStyles.css", "string")} />
  <Include src="./src/hr.rsx" />
  <Include src="./src/page2.rsx" />
  <Include src="./src/cadastroBilling.rsx" />
  <Include src="./src/bankReconciliation2.rsx" />
  <Include src="./src/login.rsx" />
  <Include src="./src/configuracoes2.rsx" />
  <Include src="./src/page4.rsx" />
  <Include src="./src/page5.rsx" />
  <Include src="./header.rsx" />
  <Include src="./src/drawerFrame1.rsx" />
  <Include src="./src/modalChangePassword.rsx" />
  <Include src="./src/modalFrame15.rsx" />
  <Include src="./src/modalFrame9.rsx" />
  <Include src="./src/modalGeneralImport.rsx" />
  <Include src="./src/modalImportOFX2.rsx" />
  <Include src="./src/modalNewUser.rsx" />
  <Include src="./src/modalSelectTenant.rsx" />
  <Include src="./sidebar.rsx" />
</App>
