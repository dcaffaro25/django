<DrawerFrame
  id="drawerAIChat"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden="{{ !switchAIChat.value }}"
  isHiddenOnMobile={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  width="medium"
>
  <Header>
    <Text
      id="drawerTitle2"
      value="### Container title"
      verticalAlign="center"
    />
    <Button
      id="drawerCloseButton2"
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
        pluginId="drawerAIChat"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <ButtonGroup
      id="buttonGroupLegacy2"
      label="Estratégia"
      value={'"auto"'}
      values={'["auto","rag","no rag"]'}
    />
    <ButtonGroup
      id="ChatLength"
      label="Tamanho"
      labels={'["low","mid","high"]'}
      value={'"auto"'}
      values="[250,3000,15000]"
    />
    <Chat
      id="llmChat4"
      _actionDisabled={{ map: { "1a": "" } }}
      _actionHidden={{ map: { "1a": "" } }}
      _actionIcon={{ map: { "1a": "line/interface-align-front" } }}
      _actionIds={["1a"]}
      _actionLabel={{ map: { "1a": "Copy" } }}
      _actionType={{ map: { "1a": "copy" } }}
      _defaultUsername="{{ current_user.fullName }}"
      _headerButtonHidden={{ "2b": "", "3c": "" }}
      _headerButtonIcon={{
        "2b": "line/interface-download-button-2",
        "3c": "line/interface-delete-bin-2",
      }}
      _headerButtonIds={["2b", "3c"]}
      _headerButtonLabel={{ "2b": "Download", "3c": "Clear history" }}
      _headerButtonType={{ "2b": "download", "3c": "clearHistory" }}
      _sessionStorageId="ad289899-c97c-40a6-a04d-0f4f2ae34b72"
      _sourceSessionStorageId={null}
      assistantName="Nord AI"
      avatarFallback="{{ current_user.fullName }}"
      avatarImageSize={32}
      avatarSrc="{{ current_user.profilePhotoUrl }}"
      emptyDescription="Send a message to chat with AI"
      emptyTitle="No messages here yet"
      placeholder="Type a message"
      queryTargetId="Chat_ask2"
      sessionStorageId="3ae3073d-8ff8-4111-b27e-c4737dbd7a47"
      showAvatar={true}
      showEmptyState={true}
      showHeader={true}
      showTimestamp={true}
      style={{ map: { background: "automatic" } }}
      title="Chat"
    >
      <Event
        event="clickAction"
        method="copyToClipboard"
        params={{ map: { value: "{{ currentMessage.value }}" } }}
        pluginId="llmChat4"
        targetId="1a"
        type="util"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="clickHeader"
        method="exportData"
        pluginId="llmChat4"
        targetId="2b"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="clickHeader"
        method="clearHistory"
        pluginId="llmChat4"
        targetId="3c"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Chat>
  </Body>
</DrawerFrame>
