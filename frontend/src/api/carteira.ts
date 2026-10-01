import api from './client'

export const carteiraAPI = {
  // Dashboard
  getDashboard: () => api.get('/api/carteira/dashboard').then(r => r.data),

  // Clientes
  getClientes: (params?: any) => api.get('/api/carteira/clientes', { params }).then(r => r.data),
  getCliente: (id: number) => api.get(`/api/carteira/clientes/${id}`).then(r => r.data),
  createCliente: (data: any) => api.post('/api/carteira/clientes', data).then(r => r.data),
  updateCliente: (id: number, data: any) => api.put(`/api/carteira/clientes/${id}`, data).then(r => r.data),

  // Emissões (Debêntures)
  getEmissoes: () => api.get('/api/carteira/emissoes').then(r => r.data),
  getEmissao: (id: number) => api.get(`/api/carteira/emissoes/${id}`).then(r => r.data),
  createEmissao: (data: any) => api.post('/api/carteira/emissoes', data).then(r => r.data),

  // Debêntures (Posições)
  getDebentures: (params?: any) => api.get('/api/carteira/debentures', { params }).then(r => r.data),
  getDebenture: (id: number) => api.get(`/api/carteira/debentures/${id}`).then(r => r.data),
  createDebenture: (data: any) => api.post('/api/carteira/debentures', data).then(r => r.data),
  updateDebenture: (id: number, data: any) => api.put(`/api/carteira/debentures/${id}`, data).then(r => r.data),
  deleteDebenture: (id: number) => api.delete(`/api/carteira/debentures/${id}`),

  // Empreendimentos
  getEmpreendimentos: () => api.get('/api/carteira/empreendimentos').then(r => r.data),
  createEmpreendimento: (data: any) => api.post('/api/carteira/empreendimentos', data).then(r => r.data),

  // Imobiliário (Posições)
  getImobiliario: (params?: any) => api.get('/api/carteira/imobiliario', { params }).then(r => r.data),
  getImobiliarioItem: (id: number) => api.get(`/api/carteira/imobiliario/${id}`).then(r => r.data),
  createImobiliario: (data: any) => api.post('/api/carteira/imobiliario', data).then(r => r.data),
  updateImobiliario: (id: number, data: any) => api.put(`/api/carteira/imobiliario/${id}`, data).then(r => r.data),

  // Fundos (Referência)
  getFundosReferencia: () => api.get('/api/carteira/fundos-referencia').then(r => r.data),
  createFundoReferencia: (data: any) => api.post('/api/carteira/fundos-referencia', data).then(r => r.data),

  // Fundos (Posições)
  getFundos: (params?: any) => api.get('/api/carteira/fundos', { params }).then(r => r.data),
  getFundo: (id: number) => api.get(`/api/carteira/fundos/${id}`).then(r => r.data),
  createFundo: (data: any) => api.post('/api/carteira/fundos', data).then(r => r.data),
  updateFundo: (id: number, data: any) => api.put(`/api/carteira/fundos/${id}`, data).then(r => r.data),

  // Estratégias
  getEstrategias: (params?: any) => api.get('/api/carteira/estrategias', { params }).then(r => r.data),
  createEstrategia: (data: any) => api.post('/api/carteira/estrategias', data).then(r => r.data),
  buscarEstrategia: (termo: string) => api.get(`/api/carteira/estrategias/busca/${termo}`).then(r => r.data),

  // Uploads
  uploadDocumento: (formData: FormData) =>
    api.post('/api/carteira/upload-documento', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data),

  // Relatórios
  gerarPDFCliente: (clienteId: number) =>
    api.get(`/api/carteira/cliente/${clienteId}/pdf`, { responseType: 'blob' }),

  exportarQualificacao: (clienteIds: number[], formato: 'xlsx' | 'pdf' = 'xlsx') =>
    api.post('/api/carteira/exportar-qualificacao', { cliente_ids: clienteIds, formato }, {
      responseType: 'blob',
    }),
}

export default carteiraAPI
