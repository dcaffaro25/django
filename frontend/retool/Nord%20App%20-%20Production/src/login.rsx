<Screen
  id="login"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle={null}
  title="login"
  urlSlug="login"
  uuid="07259391-0494-453a-aab0-44754d219437"
>
  <RESTQuery
    id="query21"
    body={
      '[{"key":"username","value":"{{ formLogin.username }}\\n"},{"key":"password","value":"{{ formLogin.password }}"}]'
    }
    bodyType="json"
    notificationDuration={4.5}
    query="https://server-production-e754.up.railway.app/login/"
    resourceDisplayName="Login Auth"
    resourceName="b3f2a741-742b-41e7-b5fe-bfa65ad99ea8"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    showSuccessToaster={false}
    type="POST"
  />
  <JavascriptQuery
    id="query22"
    notificationDuration={4.5}
    query={include("../lib/query22.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="user_login"
    body={
      '[{"key":"username","value":"{{ usernameInput.value }}"},{"key":"password","value":"{{password1.value }}"}]'
    }
    bodyType="json"
    cookies="[]"
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/login/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="run"
      params={{
        map: {
          src: '// 1) Save the login payload\nawait currentUser.setValue(user_login.data);\n\nconst SESSION_MINUTES = 30;\nconst token = user_login.data?.token;\n\nconst now = Date.now();\nconst expiresAt = now + SESSION_MINUTES * 60 * 1000;\nconst session = { token, expiresAt };\nlocalStorage.setValue("auth_session", JSON.stringify(session));\nlocalStorage.setValue("currentUser", user_login.data);\n\n// 2) Route\nconst must = !!user_login.data?.user?.must_change_password;\nconsole.log(must);\nif (must) {\n  console.log("must = true");\n  modalChangePassword.show();   // <- this is the fix\n} else {\n  console.log("must = false");\n  utils.openApp(retoolContext.appUuid, { pageName: "home" });\n}',
        },
      }}
      pluginId=""
      type="script"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="Users_get"
    cookies="[]"
    headers={
      '[{"key":"Authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/api/core/users"
    queryDisabled={'{{ currentUser.value=="" }}'}
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="User_new"
    body={
      '[{"key":"username","value":"areis"},{"key":"email","value":"areis@nordventures.com.br"},{"key":"first_name","value":"Augusto"},{"key":"last_name","value":"Reis"}]'
    }
    bodyType="json"
    cookies="[]"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/users/create/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: "{{ user_login.data }}" } }}
      pluginId="currentUser"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="openPage"
      params={{
        options: { map: { passDataWith: "urlParams" } },
        pageName: "home",
      }}
      pluginId=""
      type="util"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <Frame
    id="$main12"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    style={{
      map: {
        canvas:
          '{{ url.href.split("/").pop() == "login" ? theme.primary: theme.surfacePrimary }} ',
      },
    }}
    type="main"
  >
    <Container
      id="container24"
      _align="center"
      _gap="0px"
      _justify="center"
      _type="stack"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      style={{ border: "primary", background: "primary" }}
    >
      <Header>
        <Text
          id="containerTitle26"
          value="#### Container title"
          verticalAlign="center"
        />
      </Header>
      <View id="00030" viewKey="View 1">
        <Container
          id="container23"
          _gap="0px"
          _justify="center"
          _type="stack"
          enableFullBleed={true}
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          heightType="fixed"
          overflowType="hidden"
          padding="12px"
          showBody={true}
          style={{ map: { background: "surfacePrimary" } }}
        >
          <Header>
            <Text
              id="containerTitle25"
              horizontalAlign="center"
              value="#### Container title"
              verticalAlign="center"
            />
          </Header>
          <View id="00030" viewKey="View 1">
            <Form
              id="form17"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              initialData=""
              padding="12px"
              requireValidation={true}
              resetAfterSubmit={true}
              showBody={true}
              showFooter={true}
            >
              <Header>
                <Text
                  id="formTitle30"
                  heightType="fixed"
                  value="#### Login"
                  verticalAlign="center"
                />
              </Header>
              <Body>
                <Image
                  id="image2"
                  fit="contain"
                  heightType="fixed"
                  horizontalAlign="center"
                  retoolStorageFileId="01c7ab53-6ec9-4b0a-b7b9-99b02ddd8e49"
                  src="https://picsum.photos/id/1025/800/600"
                />
                <Text
                  id="text46"
                  horizontalAlign="center"
                  value="##### Login"
                  verticalAlign="center"
                />
                <Container
                  id="group66"
                  _align="center"
                  _direction="vertical"
                  _gap="15px"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                >
                  <View id="00030" viewKey="View 1">
                    <TextInput
                      id="usernameInput"
                      formDataKey="username"
                      label="Username"
                      labelPosition="top"
                      placeholder="Enter value"
                      required={true}
                    />
                    <PasswordInput
                      id="password1"
                      label="Password"
                      labelPosition="top"
                      showTextToggle={true}
                    >
                      <Event
                        event="submit"
                        method="trigger"
                        params={{
                          map: {
                            options: {
                              object: {
                                onSuccess: null,
                                onFailure: null,
                                additionalScope: null,
                              },
                            },
                          },
                        }}
                        pluginId="user_login"
                        type="datasource"
                        waitMs="0"
                        waitType="debounce"
                      />
                    </PasswordInput>
                  </View>
                </Container>
              </Body>
              <Footer>
                <Button id="formButton18" submitTargetId="form17" text="Submit">
                  <Event
                    event="click"
                    method="trigger"
                    params={{}}
                    pluginId="user_login"
                    type="datasource"
                    waitMs="0"
                    waitType="debounce"
                  />
                </Button>
              </Footer>
            </Form>
          </View>
        </Container>
      </View>
    </Container>
  </Frame>
</Screen>
