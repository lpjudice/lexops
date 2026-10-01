// @ts-nocheck
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
// removed: dialog'
// removed: button'
// removed: input'
// removed: label'
import { Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import api from '@/api/client'

export default function UploadDocumentoModal({ clienteId, open, onOpenChange }) {
  const qc = useQueryClient()
  const [arquivo, setArquivo] = useState(null)
  const [tipo, setTipo] = useState('geral')
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState(null)

  const processarMutation = useMutation({
    mutationFn: async (file) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('tipo', tipo)
      return api.post('/api/carteira/processar-documento', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(r => r.data)
    },
    onSuccess: (data) => {
      setResultado(data.dados_extraidos)
      setErro(null)
      qc.invalidateQueries({ queryKey: ['carteira-documentos', clienteId] })
    },
    onError: (err: any) => {
      setErro(err?.response?.data?.detail || 'Erro ao processar documento')
      setResultado(null)
    },
  })

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setArquivo(file)
      processarMutation.mutate(file)
    }
  }

  const handleFechar = () => {
    setArquivo(null)
    setResultado(null)
    setErro(null)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>📄 Upload & IA - Extrair Dados de Documento</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Seletor de tipo */}
          {!resultado && !processarMutation.isPending && (
            <div>
              <Label>Tipo de Documento</Label>
              <select
                value={tipo}
                onChange={(e) => setTipo(e.target.value)}
                className="border border-gray-300 rounded px-3 py-2 w-full"
              >
                <option value="geral">Geral (auto-detectar)</option>
                <option value="debenture">Debênture/Securitização</option>
                <option value="imobiliario">Imobiliário</option>
                <option value="fundo">Fundo de Investimento</option>
              </select>
            </div>
          )}

          {/* Upload area */}
          {!resultado && (
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-500 transition">
              <label className="cursor-pointer space-y-2">
                <Upload className="h-8 w-8 mx-auto text-gray-400" />
                <span className="block text-sm text-gray-600">
                  {processarMutation.isPending ? 'Processando...' : 'Clique para enviar ou arraste um arquivo'}
                </span>
                <span className="block text-xs text-gray-500">
                  PDF, JPG, PNG (max 10MB)
                </span>
                <Input
                  type="file"
                  onChange={handleUpload}
                  disabled={processarMutation.isPending}
                  className="hidden"
                  accept="image/*,.pdf"
                />
              </label>
            </div>
          )}

          {/* Loading state */}
          {processarMutation.isPending && (
            <div className="flex items-center justify-center gap-3 py-8">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Processando documento com Claude Vision...</span>
            </div>
          )}

          {/* Erro */}
          {erro && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-red-900">Erro ao processar</p>
                <p className="text-sm text-red-700">{erro}</p>
              </div>
            </div>
          )}

          {/* Resultado */}
          {resultado && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle className="h-5 w-5 text-green-600" />
                <p className="font-medium text-green-900">Dados extraídos com sucesso!</p>
              </div>

              <div className="space-y-2 bg-white rounded p-3 text-sm max-h-64 overflow-y-auto">
                {Object.entries(resultado).map(([chave, valor]) => (
                  <div key={chave} className="grid grid-cols-3 gap-2">
                    <span className="font-medium text-gray-600">{chave}:</span>
                    <span className="col-span-2 text-gray-900 break-words">
                      {String(valor)}
                    </span>
                  </div>
                ))}
              </div>

              <p className="text-xs text-gray-500 mt-3">
                💡 Você pode copiar estes dados para preencher o formulário abaixo.
              </p>
            </div>
          )}

          {/* Botões */}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleFechar}>
              {resultado ? 'Fechar' : 'Cancelar'}
            </Button>
            {resultado && (
              <Button
                className="bg-blue-600 hover:bg-blue-700"
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify(resultado, null, 2))
                }}
              >
                📋 Copiar JSON
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
