import api from './client'

export interface RespostaEspecialista {
  chave: string
  nome: string
  resposta: string
}

export const conselhoJuridicoApi = {
  consultar: (body: { cliente_id?: string; processo_id?: string; pergunta: string }) =>
    api.post<{ respostas: RespostaEspecialista[] }>('/conselho-juridico/consultar', body).then((r) => r.data),
}
