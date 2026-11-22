// Cliente RTC mínimo (só áudio) usado pelas páginas de teste.
window.AvisaiRTC = {
  client: null,
  mic: null,
  async entrar({ app_id, channel, uid, token }, log) {
    const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
    this.client = client;
    client.on("user-published", async (user, mediaType) => {
      await client.subscribe(user, mediaType);
      if (mediaType === "audio") {
        user.audioTrack.play();
        log(`ouvindo uid ${user.uid}`);
      }
    });
    client.on("user-joined", (u) => log(`entrou no canal: uid ${u.uid}`));
    client.on("user-left", (u) => log(`saiu do canal: uid ${u.uid}`));
    await client.join(app_id, channel, token, Number(uid));
    try {
      this.mic = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true });
    } catch (e) {
      log(`ERRO: microfone indisponível (${e && (e.code || e.name || e.message)}). ` +
          `Abra esta página no Chrome em http://localhost:8000 ou https (o painel do app bloqueia o microfone).`);
      throw e;
    }
    await client.publish([this.mic]);
    log(`no canal ${channel} como uid ${uid}, microfone aberto ✅ pode falar`);
  },
  async sair(log) {
    if (this.mic) { this.mic.close(); this.mic = null; }
    if (this.client) { await this.client.leave(); this.client = null; }
    log && log("saiu do canal");
  },
};
