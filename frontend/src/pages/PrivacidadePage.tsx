const wrap: React.CSSProperties = {
  maxWidth: 820,
  margin: '0 auto',
  padding: '40px 20px 80px',
  fontFamily: 'system-ui, sans-serif',
  color: '#1f2937',
  lineHeight: 1.6,
}

const h2: React.CSSProperties = {
  fontSize: 18,
  color: '#0f766e',
  marginTop: 32,
  marginBottom: 8,
}

const small: React.CSSProperties = { color: '#6b7280', fontSize: 13 }

export default function PrivacidadePage() {
  return (
    <div style={wrap}>
      <div style={{ borderBottom: '2px solid #0d9488', paddingBottom: 16, marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 24, color: '#0f766e' }}>Política de Privacidade</h1>
        <div style={small}>Pimenta Júdice Advogados · CNPJ 10.901.611/0001-64 · última atualização: 27/09/2026</div>
      </div>

      <p>
        Esta Política de Privacidade descreve como <strong>Pimenta Júdice Advogados</strong> ("escritório", "nós")
        coleta, usa e protege dados pessoais de clientes e potenciais clientes, em conformidade com a Lei Geral de
        Proteção de Dados (Lei nº 13.709/2018 — LGPD) e com o sigilo profissional a que estamos sujeitos como
        advogados (art. 34, VII, "d", da Lei nº 8.906/1994 — Estatuto da OAB).
      </p>

      <h2 style={h2}>1. Quem é o controlador dos dados</h2>
      <p>
        Pimenta Júdice Advogados, CNPJ 10.901.611/0001-64, com atuação em Vitória/ES e Los Angeles/CA. Contato:{' '}
        <a href="mailto:pj@pimentajudice.com.br">pj@pimentajudice.com.br</a> · +55 (27) 3345-5501.
      </p>

      <h2 style={h2}>2. Dados que coletamos via WhatsApp</h2>
      <p>
        Quando você troca mensagens conosco pelo WhatsApp (número institucional do escritório), coletamos e
        processamos: seu número de telefone, nome de exibição do WhatsApp, e o conteúdo das mensagens trocadas
        (incluindo, quando aplicável, informações sobre processos e andamentos judiciais de sua titularidade que
        você já nos confiou como cliente).
      </p>

      <h2 style={h2}>3. Para que usamos esses dados</h2>
      <ul>
        <li>Notificar clientes sobre novos andamentos em processos sob nossa condução, quando o cliente optar por
          receber esse tipo de aviso;</li>
        <li>Responder dúvidas pontuais sobre o andamento processual do próprio cliente, por meio de um assistente
          automatizado com acesso restrito apenas aos dados do processo daquele cliente;</li>
        <li>Comunicação geral entre escritório e cliente no âmbito da relação contratual de prestação de serviços
          advocatícios.</li>
      </ul>
      <p>
        Não utilizamos o WhatsApp para envio de mensagens de marketing ou publicidade não solicitada.
      </p>

      <h2 style={h2}>4. Base legal (LGPD)</h2>
      <p>
        O tratamento se fundamenta na execução do contrato de prestação de serviços advocatícios (art. 7º, V, LGPD)
        e, subsidiariamente, no legítimo interesse do escritório em manter seus clientes informados sobre o
        andamento de seus próprios processos (art. 7º, IX, LGPD).
      </p>

      <h2 style={h2}>5. Compartilhamento com terceiros</h2>
      <p>
        As mensagens trafegam pela infraestrutura da Meta Platforms, Inc., operadora da WhatsApp Business Platform,
        que processa o conteúdo exclusivamente para viabilizar a entrega das mensagens, nos termos da própria
        política de privacidade da Meta. Não vendemos, alugamos ou compartilhamos seus dados com terceiros para fins
        de marketing.
      </p>

      <h2 style={h2}>6. Retenção e segurança</h2>
      <p>
        Os dados são mantidos pelo prazo necessário à prestação dos serviços contratados e ao cumprimento de
        obrigações legais e regulatórias (incluindo prazos de guarda de documentos exigidos por normas da OAB),
        armazenados em ambiente controlado com acesso restrito à equipe do escritório.
      </p>

      <h2 style={h2}>7. Sigilo profissional</h2>
      <p>
        Além das proteções da LGPD, todo o conteúdo trocado está sujeito ao sigilo profissional advocatício,
        vedando-se seu uso ou divulgação fora dos fins da relação cliente-advogado.
      </p>

      <h2 style={h2}>8. Seus direitos</h2>
      <p>
        Você pode solicitar a qualquer momento, mediante contato pelos canais indicados acima: confirmação da
        existência de tratamento, acesso aos dados, correção de dados incompletos ou desatualizados, anonimização,
        bloqueio ou eliminação de dados desnecessários, portabilidade, e revogação do consentimento para receber
        notificações via WhatsApp (o que não afeta a comunicação sobre o processo por outros canais já contratados).
      </p>

      <h2 style={h2}>9. Contato</h2>
      <p>
        Dúvidas sobre esta política ou sobre o tratamento de seus dados podem ser enviadas para{' '}
        <a href="mailto:pj@pimentajudice.com.br">pj@pimentajudice.com.br</a>.
      </p>
    </div>
  )
}
