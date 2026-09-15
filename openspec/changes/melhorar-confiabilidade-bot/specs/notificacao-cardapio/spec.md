## Purpose

Decidir o que vai para o chat do Telegram a cada execução: quais refeições são novidade,
quais mudaram desde o último aviso e quais devem ser omitidas por já terem sido enviadas
sem alteração.

## ADDED Requirements

### Requirement: Rastrear estado por refeição

O sistema SHALL identificar cada entrada de estado pelo par (data do cardápio, refeição),
independentemente de quais refeições foram pedidas na execução. Duas execuções que pedem
conjuntos diferentes de refeições MUST reconhecer as refeições que têm em comum.

#### Scenario: Prévia da noite e reconferência da manhã

- **WHEN** a execução da noite envia desjejum, almoço e jantar do dia seguinte
- **AND** na manhã seguinte uma execução pede almoço e jantar do mesmo dia, com conteúdo
  idêntico ao que foi enviado
- **THEN** nada é enviado
- **AND** o sistema termina com código de saída zero

#### Scenario: Só uma refeição mudou

- **WHEN** o almoço mudou desde o aviso anterior e o jantar continua igual
- **THEN** a mensagem enviada contém apenas o almoço
- **AND** a mensagem traz o aviso de que o cardápio mudou desde o aviso anterior

#### Scenario: Refeição inédita

- **WHEN** uma refeição pedida nunca foi enviada para aquela data
- **THEN** ela é enviada sem o aviso de mudança

### Requirement: Gravar estado somente após envio bem-sucedido

O sistema SHALL atualizar o estado apenas depois de o Telegram confirmar o recebimento.
Se o envio falhar, o estado MUST permanecer inalterado, para que a execução seguinte
tente de novo.

#### Scenario: Telegram recusa a mensagem

- **WHEN** o envio falha
- **THEN** o estado não é alterado
- **AND** o sistema termina com código de saída diferente de zero

#### Scenario: Envio parcial em múltiplas mensagens

- **WHEN** a mensagem é dividida e uma das partes falha
- **THEN** as refeições cujo envio não foi confirmado permanecem sem estado gravado

### Requirement: Descartar estado antigo

O sistema SHALL remover do arquivo de estado as entradas cuja data de cardápio seja
anterior a um período de retenção, mantendo o arquivo pequeno.

Entradas em formato não reconhecido MUST ser descartadas em vez de provocar erro.

#### Scenario: Entrada velha

- **WHEN** o estado contém uma entrada com mais de 30 dias
- **THEN** ela é removida na próxima gravação

#### Scenario: Estado de formato anterior

- **WHEN** o arquivo de estado contém chaves no formato antigo (data + lista de refeições)
- **THEN** elas são ignoradas sem erro
- **AND** as refeições daquele dia são tratadas como inéditas

#### Scenario: Arquivo de estado corrompido

- **WHEN** o arquivo de estado não é JSON válido
- **THEN** o sistema trata como estado vazio e registra um aviso

### Requirement: Tolerar falhas transitórias no envio

O sistema SHALL repetir o envio ao Telegram quando a falha for transitória — timeout,
erro de conexão, 5xx, ou limite de requisições (429), respeitando a espera pedida pela
API. Erros definitivos de configuração, como token inválido ou chat inexistente, NÃO
devem ser repetidos.

#### Scenario: Limite de requisições

- **WHEN** o Telegram responde 429 pedindo espera
- **THEN** o sistema espera o tempo indicado e tenta de novo

#### Scenario: Token inválido

- **WHEN** o Telegram responde 401
- **THEN** o sistema não repete o envio e termina com código de saída diferente de zero
