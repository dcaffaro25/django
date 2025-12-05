<Frame
  id="$header"
  enableFullBleed={null}
  isHiddenOnDesktop={false}
  isHiddenOnMobile={true}
  margin="4px 8px"
  padding="8px 12px"
  sticky={true}
  style={{
    map: {
      "primary-surface":
        '{{ url.href.split("/").pop() == "login" ? theme.primary : theme.surfacePrimary }}',
    },
  }}
  type="header"
>
  <Image
    id="image3"
    fit="contain"
    heightType="fixed"
    hidden={'{{ url.href.split("/").pop() == "login" }}'}
    retoolStorageFileId="01c7ab53-6ec9-4b0a-b7b9-99b02ddd8e49"
    src="https://picsum.photos/id/1025/800/600"
  >
    <Event
      event="click"
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
  </Image>
  <DropdownButton
    id="dropdownButton2"
    _colorByIndex={["", "", "", ""]}
    _fallbackTextByIndex={["", "", "", ""]}
    _imageByIndex={["", "", "", ""]}
    _values={["", "Action 4", "", ""]}
    hidden={'{{ url.href.split("/").pop() == "login" }}'}
    horizontalAlign="right"
    icon="bold/interface-user-single"
    itemMode="static"
    overlayMaxHeight={375}
    styleVariant="outline"
    text="{{ localStorage.values.currentUser.user.username }}"
  >
    <Option
      id="00030"
      hidden="{{ !currentUser?.value }}"
      label="Change Password"
    >
      <Event
        event="click"
        method="show"
        params={{}}
        pluginId="modalChangePassword"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Option>
    <Option
      id="61ce8"
      disabled={false}
      hidden="{{ !currentUser?.value || !currentUser.value.user.is_superuser }}"
      label="New User"
    >
      <Event
        event="click"
        method="setValue"
        params={{ map: { value: '"new"' } }}
        pluginId="SelectedUserMode"
        type="state"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="click"
        method="show"
        params={{}}
        pluginId="modalNewUser"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Option>
    <Option
      id="00031"
      hidden="{{ !currentUser?.value || !currentUser.value.user.is_superuser }}"
      label="Force Change Password"
    >
      <Event
        event="click"
        method="show"
        params={{}}
        pluginId="modalChangePassword"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Option>
    <Option id="00032" hidden="{{ !currentUser?.value }}" label="Logout">
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="user_logout"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Option>
  </DropdownButton>
</Frame>
