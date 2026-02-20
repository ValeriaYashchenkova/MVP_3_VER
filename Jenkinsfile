pipeline {
    agent {
        kubernetes {
            inheritFrom 'python'
            defaultContainer 'python-builder'
        }
    }

    triggers {
        pollSCM('')  // автоматический запуск при изменениях в репозитории
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
    }

    parameters {
        string(
            name: 'BRANCH_NAME',
            defaultValue: 'master',
            description: 'Ветка для проверки дубликатов (например feature/duplicates-test)'
        )
    }

    environment {
        PATH = "/var/lib/jenkins/.local/bin:$PATH"
        ALLURE_RESULTS = "allure-results"
        TESTOPS_ENDPOINT = 'https://testops.moscow.alfaintra.net'
        TESTOPS_PROJECT_ID = '643'
        TESTOPS_SERVER_ID = 'testops'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "${params.BRANCH_NAME}"]],
                    userRemoteConfigs: [[
                        url: 'https://git.moscow.alfaintra.net/scm/bialm_ft/bialm_ft_auto.git',
                        credentialsId: 'login_password_for_repo_bitbucket'
                    ]]
                ])
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python -m venv venv || true
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install oracledb gitpython requests tomli
                '''
            }
        }

        stage('Run Duplicate Checks') {
            steps {
                sh '''
                    . venv/bin/activate
                    rm -rf ${ALLURE_RESULTS}
                    mkdir -p ${ALLURE_RESULTS}
                    python run_test.py --branch ${BRANCH_NAME}
                '''
            }
        }
    }

    post {
        always {
            allure([
                includeProperties: false,
                reportBuildPolicy: 'ALWAYS',
                results: [[path: "${ALLURE_RESULTS}"]]
            ])

            script {
                try {
                    echo "Uploading results to Allure TestOps (project 643)..."
                    withAllureUpload(
                        credentialsId: 'testops-token',
                        name: "Duplicate Checks #${BUILD_NUMBER} | ${BRANCH_NAME}",
                        projectId: '643',
                        results: [[path: "${WORKSPACE}/allure-results"]],
                        serverId: 'testops',
                        tags: "${BRANCH_NAME}, sql-duplicates-check"
                    ) {
                        echo "Allure TestOps upload completed"
                    }
                } catch (Exception e) {
                    echo "Failed to upload to Allure TestOps: ${e}"
                }
            }

            archiveArtifacts artifacts: "${ALLURE_RESULTS}/**", allowEmptyArchive: true
            cleanWs()
        }
    }
}
