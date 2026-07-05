import api from './client'

export interface RespostaEspecialista {
  chave: string
  nome: string
  resposta: string
}

export interface MensagemConselho {
  role: 'user' | 'model'
  content: string
}

export const conselhoJuridicoApi = {
  consultar: (body: { cliente_id?: string; processo_id?: string; pergunta: string }) =>
    api.post<{ respostas: RespostaEspecialista[] }>('/conselho-juridico/consultar', body).then((r) => r.data),

  perguntarUm: (body: {
    cliente_id?: string
    processo_id?: string
    chave: string
    pergunta: string
    historico: MensagemConselho[]
  }) =>
    api.post<RespostaEspecialista>('/conselho-juridico/perguntar-um', body).then((r) => r.data),
}
