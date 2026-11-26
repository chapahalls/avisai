// Cliente LiveKit mínimo (áudio bidirecional) usado pelas páginas de demonstração.
window.AvisaiLiveKit = {
  room: null,
  async entrar({ url, token }, log) {
    const { Room, RoomEvent, Track } = LivekitClient;
    const room = new Room();
    this.room = room;
    room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
      if (track.kind === Track.Kind.Audio) {
        const audio = track.attach();
        document.body.appendChild(audio);
        audio.autoplay = true;
        log(`ouvindo ${participant.identity}`);
      }
    });
    room.on(RoomEvent.ParticipantConnected, (participant) => log(`entrou na sala: ${participant.identity}`));
    room.on(RoomEvent.ParticipantDisconnected, (participant) => log(`saiu da sala: ${participant.identity}`));
    await room.connect(url, token);
    try {
      await room.localParticipant.setMicrophoneEnabled(true);
    } catch (e) {
      log(`ERRO: microfone indisponível (${e?.message || e}). Abra em localhost ou HTTPS.`);
      throw e;
    }
    log(`conectado à sala ${room.name}; microfone aberto ✅ pode falar`);
  },
  async sair(log) {
    if (this.room) {
      await this.room.disconnect();
      this.room = null;
    }
    log?.("saiu da sala LiveKit");
  },
};
