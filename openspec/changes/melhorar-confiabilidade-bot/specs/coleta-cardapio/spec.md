## Purpose

Obter a página de cardápio do RU da UFES Alegre e convertê-la em blocos de refeição
estruturados, distinguindo com clareza três situações: cardápio disponível, ausência
legítima de cardápio, e falha (rede fora do ar ou página cuja estrutura o bot não
reconhece mais).

## ADDED Requirements

### Requirement: Distinguir falha de parser de ausência de cardápio

O sistema SHALL tratar "a página baixou mas nenhum bloco de refeição foi reconhecido"
como falha, e não como ausência de cardápio. Nessa situação o processo MUST terminar
com código de saída diferente de zero, mesmo quando a execução pede silêncio para dias
sem cardápio, de modo que o agendador acuse o erro.

Uma página que baixou e foi reconhecida, mas cujos blocos não contêm nenhuma das
refeições pedidas, NÃO é falha: é ausência de cardápio.

#### Scenario: Estrutura da página mudou

- **WHEN** a página é baixada com sucesso e nenhum cabeçalho de refeição é reconhecido
- **THEN** o sistema termina com código de saída diferente de zero
- **AND** registra no log que a estrutura não foi reconhecida e como inspecioná-la
- **AND** nenhuma mensagem é enviada ao Telegram

#### Scenario: Dia sem cardápio publicado

- **WHEN** a página é baixada, blocos de refeição são reconhecidos, mas nenhum
  corresponde ao campus e às refeições pedidas
- **THEN** o sistema termina com código de saída zero
- **AND** não envia mensagem quando a execução pede silêncio para dias vazios

#### Scenario: Página vazia mas íntegra

- **WHEN** a página declara explicitamente que não há cardápio para a data
- **THEN** o sistema termina com código de saída zero, sem sinalizar falha

### Requirement: Tolerar falhas transitórias de rede

O sistema SHALL repetir uma requisição HTTP que falhou por erro transitório — timeout,
erro de conexão, ou resposta 5xx — antes de desistir, com espera crescente entre as
tentativas. Erros definitivos, como 404, NÃO devem ser repetidos.

Esgotadas as tentativas, o sistema MUST terminar com código de saída diferente de zero
e registrar a última falha.

#### Scenario: Servidor responde 502 e depois 200

- **WHEN** a primeira tentativa de baixar a página recebe 502
- **THEN** o sistema espera e tenta de novo
- **AND** ao receber 200 segue o fluxo normal, sem sinalizar erro

#### Scenario: Servidor fora do ar

- **WHEN** todas as tentativas de baixar a página falham
- **THEN** o sistema termina com código de saída diferente de zero
- **AND** registra quantas tentativas fez e qual foi o último erro

#### Scenario: Data inexistente

- **WHEN** a requisição recebe 404
- **THEN** o sistema não repete a requisição

### Requirement: Sinalizar rótulo de seção desconhecido

O sistema SHALL registrar um aviso quando encontrar uma linha que tem a forma de um
rótulo de seção mas não está na lista de categorias conhecidas, em vez de anexá-la em
silêncio como item da seção anterior.

O conteúdo continua sendo entregue — o aviso é observabilidade, não motivo de falha.

#### Scenario: Rótulo novo aparece no site

- **WHEN** a página traz uma seção rotulada "Molho", ausente da lista de categorias
- **THEN** o sistema registra um aviso nomeando o rótulo não reconhecido
- **AND** a execução continua normalmente e a mensagem é enviada

### Requirement: Preservar a verificação de certificado

O sistema SHALL manter a verificação TLS ativa ao baixar a página, complementando o
bundle de certificados com o intermediário da RNP/ICPEdu quando ele estiver disponível.
Desativar a verificação NÃO é um caminho aceitável de contorno.

#### Scenario: Cadeia incompleta do servidor da UFES

- **WHEN** o servidor não envia o certificado intermediário e o arquivo local existe
- **THEN** o download é feito com verificação ativa usando o bundle combinado

#### Scenario: Intermediário ausente e handshake falha

- **WHEN** o arquivo do intermediário não existe e a verificação TLS falha
- **THEN** o sistema termina com erro explicando como obter o certificado
- **AND** não tenta baixar a página sem verificação
