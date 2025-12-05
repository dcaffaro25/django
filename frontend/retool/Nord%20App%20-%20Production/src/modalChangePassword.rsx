<ModalFrame
  id="modalChangePassword"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden="true"
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction="{{ !currentUser.value.user.must_change_password }}"
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
>
  <Header>
    <Image
      id="image4"
      fit="contain"
      heightType="fixed"
      retoolStorageFileId="01c7ab53-6ec9-4b0a-b7b9-99b02ddd8e49"
      src="https://picsum.photos/id/1025/800/600"
      srcType="retoolStorageFileId"
    />
    <Button
      id="modalCloseButton44"
      ariaLabel="Close"
      hidden={'{{ url.href.split("/").pop() == "login" }}'}
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ map: { border: "transparent" } }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ map: { hidden: true } }}
        pluginId="modalChangePassword"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form18"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      showBody={true}
      showFooter={true}
      style={{ map: { border: "surfacePrimary" } }}
    >
      <Header>
        <Text
          id="formTitle31"
          heightType="fixed"
          value="#### Login"
          verticalAlign="center"
        />
      </Header>
      <Body>
        <Text
          id="text47"
          horizontalAlign="center"
          value="##### Change Password"
          verticalAlign="center"
        />
        <Container
          id="group65"
          _align="center"
          _direction="vertical"
          _flexWrap={true}
          _gap="10px"
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
            <Select
              id="select20"
              captionByIndex="{{ item.email }}"
              data="{{ users_get.data }}"
              disabled="{{ !currentUser.value.user.is_superuser }}"
              disabledByIndex=""
              emptyMessage="No options"
              formDataKey="username"
              hidden="{{ !currentUser.value.user.is_superuser }}"
              hiddenByIndex=""
              label="Username"
              labelPosition="top"
              labels="{{ `${item.first_name} ${item.last_name}` }}"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ currentUser.value.user.id }}"
              values="{{ item.id }}"
            />
            <PasswordInput
              id="password2"
              disabled="{{ currentUser.value.user.id == select20.value ? false : currentUser.value.user.is_superuser }}"
              hidden="{{ currentUser.value.user.id == select20.value ? false : currentUser.value.user.is_superuser }}"
              label="Old Password"
              labelPosition="top"
              required={true}
              showTextToggle={true}
            >
              <Event
                event="submit"
                method="focus"
                params={{}}
                pluginId="password3"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
            </PasswordInput>
            <PasswordInput
              id="password3"
              label="New Password"
              labelPosition="top"
              required={true}
              showTextToggle={true}
            >
              <Event
                enabled="{{ currentUser.value.user.id == select20.value ? true : !currentUser.value.user.is_superuser }}"
                event="submit"
                method="trigger"
                params={{}}
                pluginId="user_change_password"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
              <Event
                enabled="{{ currentUser.value.user.id == select20.value ? false : currentUser.value.user.is_superuser }}"
                event="submit"
                method="trigger"
                params={{}}
                pluginId="user_admin_reset"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
            </PasswordInput>
          </View>
        </Container>
      </Body>
      <Footer>
        <Button id="formButton19" submitTargetId="form18" text="Submit">
          <Event
            enabled="{{ currentUser.value.user.id == select20.value ? true : !currentUser.value.user.is_superuser }}"
            event="click"
            method="trigger"
            params={{}}
            pluginId="user_change_password"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
          <Event
            enabled="{{ currentUser.value.user.id == select20.value ? false : currentUser.value.user.is_superuser }}"
            event="click"
            method="trigger"
            params={{}}
            pluginId="user_admin_reset"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
      </Footer>
    </Form>
  </Body>
</ModalFrame>
