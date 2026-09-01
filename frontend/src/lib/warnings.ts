export function translateSystemWarning(text: string): string {
  if (/incompatible feature schema/i.test(text)) {
    return "I modelli non sono allineati. Rigenera le previsioni.";
  }
  if (/more than 24 hours old/i.test(text)) {
    return "Le previsioni hanno più di 24 ore. Aggiorna i dati.";
  }
  if (/no upcoming fixtures/i.test(text)) {
    return "Non ci sono partite in calendario nei prossimi 30 giorni. Aggiorna i dati.";
  }
  if (/no successful data ingestion/i.test(text)) {
    return "Non è stato completato alcun aggiornamento dati. Avvialo da questa pagina.";
  }
  if (/no successful prediction run/i.test(text)) {
    return "Non ci sono previsioni utilizzabili. Rigenerale da questa pagina.";
  }
  if (/no champion model/i.test(text)) {
    return "Non ci sono modelli attivi. Rigenera le previsioni.";
  }
  if (/blocking data-quality issues/i.test(text)) {
    return "Ci sono problemi bloccanti nei dati. Aggiorna i dati e riprova.";
  }
  return text
    .replace(/[\u2014\u2013\u2192\u2190\u2194]/g, " ")
    .replaceAll(";", ".")
    .replace(/\s+/g, " ")
    .trim();
}
