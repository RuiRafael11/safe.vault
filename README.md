# Safe.Vault — Cofre Local

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Plataforma](https://img.shields.io/badge/Plataforma-Windows-0078D4)
![Versão](https://img.shields.io/badge/Vers%C3%A3o-1.3.0-2EA043)

Gestor de palavras-passe para Windows, totalmente offline. Os dados ficam num
ficheiro `.vault` controlado pelo utilizador; não existe conta, servidor ou
sincronização automática.

Versão atual: **1.3.0**.

## O que faz

Guarda credenciais com nome, utilizador, palavra-passe, endereço, categoria,
notas e favorito. Permite pesquisar e organizar as entradas, gerar palavras-passe,
copiar campos e exportar uma cópia cifrada do cofre.

## Como funciona

1. Ao criar um cofre, escolhes o ficheiro `.vault` e uma palavra-passe mestra.
2. O scrypt deriva uma chave de 256 bits dessa palavra-passe com um salt aleatório.
3. O AES-256-GCM cifra o conteúdo e permite detetar alterações ao texto cifrado.
4. Ao desbloquear, a aplicação deriva novamente a chave e decifra os dados
   localmente para a sessão. A palavra-passe mestra não fica guardada no ficheiro.
5. Ao guardar, o programa cifra novamente os dados com um nonce novo e substitui
   o ficheiro através de uma gravação atómica. Ao bloquear, limpa a sessão que controla.

O ficheiro contém os parâmetros criptográficos e o conteúdo cifrado. As
preferências de interface e o caminho do último cofre ficam separadamente em
`%LOCALAPPDATA%\Cofre Local\preferences.json`; as credenciais ficam no cofre cifrado.

## Interface

A interface desktop é construída com Flet:

- glassmorphism discreto, botões em cápsula e tipografia Inter incluída;
- temas Pearl, Midnight, Aurora e Graphite;
- transições curtas que respeitam automaticamente a preferência de animações
  do Windows, sem adicionar um botão de “menos animações”;
- pesquisa, filtros, ordenação por nome, recentes ou favoritos, edição em página
  própria e gerador configurável de palavras-passe.

## Segurança

- Cofre completo cifrado com AES-256-GCM.
- Chave derivada da palavra-passe mestra com scrypt (`N=2^17`, `r=8`, `p=1`)
  e salt aleatório.
- Nonce aleatório novo em cada gravação.
- Bloqueio automático configurável entre 1 e 60 minutos.
- Clipboard limpo após 30 segundos, desde que o conteúdo não tenha sido
  substituído entretanto.
- Cópia `.backup`, também cifrada, antes de trocar a palavra-passe mestra.
- Apenas uma instância pode abrir o mesmo ficheiro de cofre de cada vez.
- Pesquisa nunca indexa o conteúdo das palavras-passe.

A palavra-passe mestra não é guardada e não pode ser recuperada.

## Utilização

Execute `CofreLocal.exe`. Na primeira utilização, escolha **Criar novo
cofre** e use uma palavra-passe mestra longa e única.

Para levar o cofre para outro computador sem cloud:

1. Em **Definições**, escolha **Exportar cópia cifrada**.
2. Transfira o ficheiro `.vault` por uma pen USB ou outro meio sob o seu controlo.
3. No segundo computador, abra a aplicação e selecione esse ficheiro.

Evite editar simultaneamente duas cópias do mesmo cofre: esta versão é offline
e não tenta combinar alterações.

## Cópias de segurança e recuperação

Antes de uma gravação que substitui o ficheiro, o Cofre Local tenta guardar a
versão anterior em `cofre.vault.backup`. Essa cópia continua cifrada. Para a
restaurar, feche o cofre, faça uma cópia de segurança dos dois ficheiros e
substitua o ficheiro `.vault` pelo `.vault.backup`; abra então o ficheiro
restaurado normalmente.

Depois de alterar a palavra-passe mestra, a cópia `.backup` contém a versão
anterior e deve ser aberta com a **palavra-passe mestra antiga**. O ficheiro
principal passa a usar a nova palavra-passe.

Se uma gravação não puder ser concluída antes do bloqueio, a aplicação pode
oferecer um rascunho de recuperação cifrado na abertura seguinte. Os rascunhos
de edição que ainda não foram guardados existem apenas na página atual; voltar,
bloquear ou fechar a aplicação descarta-os e limpa os campos da interface.

## Limites e privacidade

O Cofre Local funciona offline: não envia o cofre, a palavra-passe mestra nem
as pesquisas para um serviço. O bloqueio limpa chaves, dados da sessão e campos
sensíveis que a aplicação controla, mas não pode prometer apagar todas as
cópias transitórias que o sistema operativo, bibliotecas ou hardware possam
manter na memória. Guarde cópias de segurança num local seguro e controle quem
pode aceder ao computador.

## Desenvolvimento

Requer Windows e Python 3.14. A instalação inicial das dependências precisa de
Internet; a utilização do cofre é local. Num checkout novo:

```powershell
git clone https://github.com/RuiRafael11/safe.vault.git
cd safe.vault
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python run_cofre.py
```

Se o PowerShell impedir a ativação, usa diretamente
`.\.venv\Scripts\python.exe` em vez de `python` nos comandos seguintes.

### Organização do código

| Caminho | Responsabilidade |
| --- | --- |
| `src/cofre_local/vault.py` | Cifragem, validação, ficheiros, backups e sessões |
| `src/cofre_local/ui_flet/` | Interface, temas, componentes e preferências |
| `tests/` | Testes de armazenamento, segurança, interface e versão |
| `tools/build.ps1` | Testes e criação do executável para Windows |
| `docs/SEGURANCA.md` | Limites de segurança e recuperação |

Os testes usam dados sintéticos e ficheiros temporários. Não precisam de abrir
um cofre pessoal. Consulta também [Segurança e recuperação](docs/SEGURANCA.md)
e as [alterações da versão 1.3.0](docs/CHANGELOG.md).

Para criar o executável de distribuição e respetivos metadados:

```powershell
.\tools\build.ps1 -Python .\.venv\Scripts\python.exe
```

O comando executa primeiro os testes e produz `outputs/CofreLocal.exe`,
`outputs/CofreLocal-SHA256.txt` e `outputs/CofreLocal-version.json`. O binário
não deve ser colocado num repositório de código.

## Dependências de terceiros

A aplicação inclui a fonte Inter sob a SIL Open Font License 1.1. O texto da
licença está em `assets/fonts/OFL-Inter.txt`.

A licença da aplicação Cofre Local ainda está por definir.
