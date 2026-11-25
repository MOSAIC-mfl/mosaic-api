// Deploy the live MOSAIC API on the CIAT server (docs/deployment.md).
//
//   1. SSH to the server.
//   2. Update /opt/mosaic-api to origin/main (clone it the first time) and install the pinned
//      dependencies into the miniforge environment "mosaic-api" (deploy/server.sh install).
//   3. Harvest every source into state/snapshot.json (deploy/server.sh harvest). A source that
//      fails keeps its previous records; the build is then UNSTABLE (yellow), not failed.
//   4. Restart the API on port 4201 and wait for /health (deploy/server.sh restart).
//
// It runs on every push to main (pollSCM) and once a day, so changes in the catalogue and in the
// CDH reach the API. The API reads the snapshot when it starts, which is why each run restarts it.
//
// Jenkins credentials (change the ids below if they are named differently):
//   mosaic_api_host    Secret text: the server's host name or IP
//   mosaic_api_deploy  SSH Username with private key: the SSH user that owns /opt/mosaic-api and
//                      its private key (its public key in that user's ~/.ssh/authorized_keys);
//                      a passphrase on the key is supported

// Run a command on the server over SSH and return its output. The private key is only on disk
// inside withCredentials, so every call opens it there.
def runRemote(String command) {
    withCredentials([sshUserPrivateKey(credentialsId: 'mosaic_api_deploy', keyFileVariable: 'SSH_KEY',
                                       usernameVariable: 'SSH_USER', passphraseVariable: 'SSH_PASSPHRASE')]) {
        // read through env: a variable the credential does not set (no passphrase) is null there,
        // while a bare SSH_PASSPHRASE would fail with "No such property"
        def remote = [
            name: env.host,
            host: env.host,
            user: env.SSH_USER,
            identityFile: env.SSH_KEY,
            allowAnyHosts: true
        ]
        if (env.SSH_PASSPHRASE) {
            remote.passphrase = env.SSH_PASSPHRASE
        }
        return sshCommand(remote: remote, command: command)
    }
}

pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    triggers {
        pollSCM('H/15 * * * *')   // a push to main deploys within 15 minutes
        cron('H 6 * * *')         // daily: CDH changes and catalogue merges
    }

    environment {
        host = credentials('mosaic_api_host')
        APP_DIR = '/opt/mosaic-api'
        REPO_URL = 'https://github.com/MOSAIC-mfl/mosaic-api.git'
        BRANCH = 'main'
        // read by deploy/server.sh
        SERVER_ENV = 'MOSAIC_API_HOME=/opt/mosaic-api MOSAIC_API_PORT=4201 CONDA_ENV=mosaic-api'
    }

    stages {
        stage('SSH to the server') {
            steps {
                script {
                    try {
                        runRemote("echo 'Connection successful!' && hostname")
                    } catch (Exception e) {
                        error("Failed to establish SSH connection: ${e.message}")
                    }
                }
            }
        }

        stage('Update code and dependencies') {
            steps {
                script {
                    try {
                        runRemote("""
                            set -e
                            if [ ! -d ${env.APP_DIR}/.git ]; then
                                git clone --branch ${env.BRANCH} ${env.REPO_URL} ${env.APP_DIR}
                            fi
                            cd ${env.APP_DIR}
                            git fetch origin ${env.BRANCH}
                            git checkout ${env.BRANCH}
                            # fast-forward only: never deploy over local changes on the server
                            git merge --ff-only origin/${env.BRANCH}
                            echo "Code: \$(git log -1 --format='%h %s')"
                            ${env.SERVER_ENV} bash deploy/server.sh install
                        """)
                    } catch (Exception e) {
                        error("Failed to update the code: ${e.message}")
                    }
                }
            }
        }

        stage('Harvest') {
            steps {
                script {
                    def out = ''
                    try {
                        out = runRemote("cd ${env.APP_DIR} && ${env.SERVER_ENV} bash deploy/server.sh harvest")
                    } catch (Exception e) {
                        error("Harvest failed and there is no previous snapshot: ${e.message}")
                    }
                    if (out.contains('HARVEST_EXIT=2')) {
                        unstable('A source failed and kept its previous records (see the harvest output above)')
                    } else if (out.contains('HARVEST_EXIT=1')) {
                        unstable('Every source failed: the API keeps serving the previous snapshot')
                    }
                }
            }
        }

        stage('Restart API') {
            steps {
                script {
                    try {
                        runRemote("cd ${env.APP_DIR} && ${env.SERVER_ENV} bash deploy/server.sh restart")
                    } catch (Exception e) {
                        error("Failed to restart the API: ${e.message}")
                    }
                }
            }
        }
    }

    post {
        failure {
            echo 'Pipeline failed: the API was not (re)started; see the stage that failed.'
        }
        unstable {
            echo 'API deployed, but at least one source could not be harvested.'
        }
        success {
            echo 'MOSAIC API deployed: http://<server>:4201/health'
        }
    }
}
