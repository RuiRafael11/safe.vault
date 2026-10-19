# Segurança e recuperação

O Cofre Local cifra todo o conteúdo do ficheiro `.vault` com AES-256-GCM. A
chave é derivada localmente da palavra-passe mestra por scrypt; a palavra-passe
mestra não é guardada nem existe recuperação para uma palavra-passe esquecida.

O programa funciona offline e bloqueia o ficheiro para que uma segunda
instância não o abra em simultâneo. Mantém também uma verificação do ficheiro
para recusar gravações se o cofre tiver mudado fora da sessão atual.

## Restaurar uma cópia `.backup`

1. Feche o Cofre Local e faça uma cópia segura do `.vault` e do `.vault.backup`.
2. Renomeie ou mova o ficheiro `.vault` atual.
3. Mude o nome de `cofre.vault.backup` para `cofre.vault`.
4. Abra o ficheiro restaurado no Cofre Local.

Uma `.backup` criada ao mudar a palavra-passe mestra é uma cópia da versão
anterior: abra-a com a palavra-passe mestra antiga. A versão principal usa a
nova palavra-passe.

Os campos de um rascunho que ainda não foi guardado são descartados ao voltar,
bloquear ou fechar a aplicação. Isto reduz a retenção na interface, mas não é
uma promessa de eliminação integral da memória: o sistema operativo, as
bibliotecas e o hardware podem manter cópias transitórias.
