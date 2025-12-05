<ModalFrame
  id="modalNewUser"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden="true"
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
  size="large"
>
  <Header>
    <Text
      id="modalTitle40"
      value={
        '### {{ SelectedUserMode.value=="new" ? "Novo " : "Editar "}}Usuário'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton45"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ map: { border: "transparent" } }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ map: { hidden: true } }}
        pluginId="modalNewUser"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form19"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ table50.selectedRow }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <Header>
        <Text id="formTitle32" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <TextInput
          id="emailInput2"
          formDataKey="email"
          iconBefore="bold/mail-send-envelope"
          label="Email"
          labelPosition="top"
          patternType="email"
          placeholder="you@example.com"
          required={true}
          value={
            '{{ SelectedUserMode.value=="new" ? "" : usernameInput2.selectedItem.email }}'
          }
        />
        <NumberInput
          id="idInput"
          currency="USD"
          disabled="false"
          formDataKey=""
          inputValue={0}
          label="ID"
          labelPosition="top"
          placeholder="Enter value"
          readOnly="true"
          required={true}
          showSeparators={true}
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.id }}'
          }
        />
        <Select
          id="usernameInput2"
          allowCustomValue={'{{ SelectedUserMode.value=="new" }}'}
          captionByIndex="{{ item.email }}"
          data={'{{ SelectedUserMode.value=="new" ? [""] : users_get.data }}'}
          emptyMessage="No options"
          formDataKey="username"
          label="Username"
          labelPosition="top"
          labels="{{ `${item.first_name} ${item.last_name}` }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value={'""'}
          values="{{ item.id }}"
        />
        <TextInput
          id="lastNameInput"
          formDataKey="last_name"
          label="Last name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.last_name }}'
          }
        />
        <TextInput
          id="firstNameInput"
          formDataKey="first_name"
          label="First name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.first_name }}'
          }
        />
        <TextInput
          id="lastLoginInput"
          disabled="false"
          formDataKey=""
          inputTooltip="`Enter` to save, `Esc` to cancel"
          label="Last login"
          labelPosition="top"
          placeholder="Enter value"
          readOnly="true"
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.last_login }}'
          }
        />
        <TextInput
          id="emailLastSentAtInput"
          disabled="false"
          formDataKey=""
          label="Email last sent at"
          labelPosition="top"
          patternType="email"
          placeholder="Enter value"
          readOnly="true"
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.email_last_sent_at }}'
          }
        />
        <TextInput
          id="dateJoinedInput"
          disabled="false"
          formDataKey=""
          inputTooltip="`Enter` to save, `Esc` to cancel"
          label="Date joined"
          labelPosition="top"
          placeholder="Enter value"
          readOnly="true"
          value={
            '{{ SelectedUserMode.value=="new" ? "" :  usernameInput2.selectedItem.date_joined }}'
          }
        />
        <Container
          id="group67"
          _flexWrap={true}
          _gap="0px"
          _justify="space-between"
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
            <Switch
              id="isSuperuserInput"
              disabled="{{ !currentUser.value.user.is_superuser }}"
              formDataKey="is_superuser"
              label="Is superuser"
              value={
                '{{ SelectedUserMode.value=="new" ? false : (usernameInput2.selectedItem.is_superuser) }}'
              }
            />
            <Switch
              id="isStaffInput"
              disabled="{{ !currentUser.value.user.is_superuser }}"
              formDataKey="is_staff"
              label="Is staff"
              value={
                '{{ SelectedUserMode.value=="new" ? false : (isSuperuserInput.value || usernameInput2.selectedItem.is_staff) }}'
              }
            />
            <Switch
              id="isActiveInput6"
              formDataKey="is_active"
              label="Is active"
              value={
                '{{ SelectedUserMode.value=="new" ? false :  usernameInput2.selectedItem.is_active }}'
              }
            />
            <Switch
              id="mustChangePasswordInput"
              formDataKey="must_change_password"
              label="Must change password"
              value={
                '{{ SelectedUserMode.value=="new" ? true :  usernameInput2.selectedItem.must_change_password }}'
              }
            />
          </View>
        </Container>
        <Multiselect
          id="groupsInput"
          disabled="true"
          emptyMessage="No options"
          formDataKey="groups"
          itemMode="static"
          label="Groups"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select options"
          required={true}
          showSelectionIndicator={true}
          values={null}
          wrapTags={true}
        >
          <Option id="00030" value="Option 1" />
          <Option id="00031" value="Option 2" />
          <Option id="00032" value="Option 3" />
        </Multiselect>
        <Multiselect
          id="userPermissionsInput"
          disabled="true"
          emptyMessage="No options"
          formDataKey="user_permissions"
          itemMode="static"
          label="User permissions"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select options"
          required={true}
          showSelectionIndicator={true}
          values={null}
          wrapTags={true}
        >
          <Option id="00030" value="Option 1" />
          <Option id="00031" value="Option 2" />
          <Option id="00032" value="Option 3" />
        </Multiselect>
        <PasswordInput
          id="password4"
          disabled="true"
          formDataKey="password"
          hidden="true"
          label="Password"
          labelPosition="top"
          placeholder="••••••••••"
          showTextToggle={true}
          value="{{ usernameInput2.selectedItem.password }}"
        />
      </Body>
    </Form>
  </Body>
  <Footer>
    <Button
      id="formButton20"
      hidden={'{{ SelectedUserMode.value=="new" ? true : false}}'}
      submitTargetId=""
      text="Edit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="users_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="formButton21"
      hidden={'{{ SelectedUserMode.value=="new" ? false : true}}'}
      submitTargetId=""
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="users_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
