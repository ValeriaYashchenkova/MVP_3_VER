pipeline {
    agent {
        kubernetes {
            inheritFrom 'python'
            defaultContainer 'python-builder'
        }
    }

    triggers {
        pollSCM('')  // следит за изменениями в репозитории
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
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
            # Устанавливаем python3-venv, если его нет (для Debian/Ubuntu-based образов)
            apt-get update && apt-get install -y python3-venv || true
            
            # Определяем, какая команда python доступна
            if command -v python3 &> /dev/null; then
                PYTHON_CMD=python3
            elif command -v python &> /dev/null; then
                PYTHON_CMD=python
            else
                echo "Python not found!"
                exit 1
            fi
            
            $PYTHON_CMD -m venv venv || true
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
            // 1. Локальный Allure-отчёт в Jenkins
            allure([
                includeProperties: false,
                reportBuildPolicy: 'ALWAYS',
                results: [[path: "${ALLURE_RESULTS}"]]
            ])

            // 2. Загрузка в Allure TestOps — исправленный шаг разработчика
            script {
                try {
                    echo "Uploading results to Allure TestOps (project 643)..."
                    withAllureUpload(
                        credentialsId: 'allure-token',
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
                    // Билд НЕ падает, если TestOps недоступен
                }
            }

            archiveArtifacts artifacts: "${ALLURE_RESULTS}/**", allowEmptyArchive: true
            cleanWs()
        }
    }
}
