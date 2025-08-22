const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const fse = require('fs-extra');
const chokidar = require('chokidar');

const watch = process.argv.includes('--watch');
const dev = process.argv.includes('--dev');

/** @type {import('esbuild').BuildOptions} */
const commonConfig = {
    bundle: true,
    minify: !dev,
    sourcemap: dev ? 'inline' : false,
    format: 'iife',
    target: ['chrome90'],
    logLevel: 'info',
    loader: {'.ts': 'ts', '.js': 'js'},
    define: {
        '__PROD__': JSON.stringify(!dev)
    },
};

// Development properties to add to manifest.json in dev mode
const devManifestObject = {
    "web_accessible_resources": [
        {
            "resources": [
                "test.html",
                "manual_input.html",
                "js/manual_input.js"
            ],
            "matches": [
                "<all_urls>"
            ]
        }
    ]
};

/**
 * Processes manifest.json by adding a development object if in dev mode
 * @param {Object} devObject - Object to add to manifest in dev mode
 * @param isFirefox - Whether we are processing for Firefox
 * @returns {Promise<void>}
 */
async function processManifest(devObject, isFirefox) {
    const manifestSrc = 'manifest.json';
    const manifestDest = `${isFirefox ? "dist_ff" : "dist"}/manifest.json`;

    try {
        // Read the manifest file
        const manifest = await fse.readJson(manifestSrc);

        // Add or remove dev object based on mode
        if (dev && devObject) {
            console.log('Adding development properties to manifest.json');
            Object.assign(manifest, devObject);
        }

        // Firefox need to use scripts for background
        if (isFirefox) {
            manifest.background.scripts = [manifest.background.service_worker]
            delete manifest.background.service_worker

            // Need to add ID manually
            manifest.browser_specific_settings = {"gecko": {"id": "{d409797b-0e11-4b68-bd0a-1dea741e0d03}"}}

            // Replace name because of a 45-character limit
            manifest.name = manifest.name.replace("Smart Job Search & Application Assistant", "Smart Job Search/Apply Asst.");
        }

        // Write the processed manifest
        await fse.writeJson(manifestDest, manifest, {spaces: 2});
        console.log(`Processed and copied manifest.json to ${manifestDest}`);
    } catch (error) {
        console.error('Error processing manifest.json:', error);
        throw error;
    }
}

function clearFolder(folderPath) {
    // Check if directory exists
    if (!fs.existsSync(folderPath)) {
        console.log(`Directory doesn't exist: ${folderPath}`);
        return;
    }

    // Read directory contents
    const files = fs.readdirSync(folderPath);

    // Delete each file/directory
    for (const file of files) {
        const filePath = path.join(folderPath, file);

        if (fs.lstatSync(filePath).isDirectory()) {
            // Recursively clear subdirectories
            clearFolder(filePath);
            fs.rmdirSync(filePath);
        } else {
            // Delete file
            fs.unlinkSync(filePath);
        }
    }

    console.log(`Cleared folder: ${folderPath}`);
}

// Configuration for assets to copy
const assetsToCopy = {
    'chrome': [
        {src: 'images', dest: 'dist/images'},
        {src: 'popup/html', dest: 'dist/popup/html'},
        {src: 'popup/css', dest: 'dist/popup/css'},
        {src: 'content-script/css', dest: 'dist/content-script/css'},
    ],
    'firefox': [
        {src: 'images', dest: 'dist_ff/images'},
        {src: 'popup/html', dest: 'dist_ff/popup/html'},
        {src: 'popup/css', dest: 'dist_ff/popup/css'},
        {src: 'content-script/css', dest: 'dist_ff/content-script/css'},
    ],
};

if (dev) {
    assetsToCopy['chrome'].push(...[
        {src: 'test.html', dest: 'dist/test.html'},
        {src: 'manual_input.html', dest: 'dist/manual_input.html'},
        {src: 'js', dest: 'dist/js'},
    ])
    assetsToCopy['firefox'].push(...[
        {src: 'test.html', dest: 'dist_ff/test.html'},
        {src: 'manual_input.html', dest: 'dist_ff/manual_input.html'},
        {src: 'js', dest: 'dist_ff/js'},
    ])
}

/**
 * Copies files and directories to specified destinations with special handling for manifest.json
 * @param {Array<{src: string, dest: string}>} copyConfigs - Array of objects with src and dest properties
 * @param {boolean} watchMode - Whether to watch for changes and recopying
 * @param isFirefox - Whether we are processing for Firefox
 */
async function copyAssets(copyConfigs, watchMode, isFirefox) {
    // Process manifest.json first with special handling
    try {
        await processManifest(devManifestObject, isFirefox);
    } catch (error) {
        console.error('Failed to process manifest.json, continuing with other assets');
    }

    if (!Array.isArray(copyConfigs) || copyConfigs.length === 0) {
        console.log('No additional assets to copy');
        return;
    }

    console.log('Copying assets...');

    // Initial copy of all assets
    for (const config of copyConfigs) {
        try {
            await fse.copy(config.src, config.dest, {
                overwrite: true
            });
            console.log(`Copied ${config.src} to ${config.dest}`);
        } catch (error) {
            console.error(`Error copying ${config.src} to ${config.dest}:`, error);
        }
    }

    // Set up watchers if in watch mode
    if (watchMode) {
        // Watch manifest.json separately
        const manifestWatcher = chokidar.watch('manifest.json', {
            persistent: true,
            ignoreInitial: true,
            awaitWriteFinish: true
        });

        manifestWatcher.on('change', async () => {
            try {
                await processManifest(devManifestObject, isFirefox);
            } catch (error) {
                console.error('Error updating manifest.json:', error);
            }
        });

        // Set up a watcher for all source paths
        const sourcePaths = copyConfigs
            .map(config => config.src);
        if (sourcePaths.length > 0) {
            const watcher = chokidar.watch(sourcePaths, {
                persistent: true,
                ignoreInitial: true,
                awaitWriteFinish: true
            });

            console.log('Watching asset files for changes...');

            // Handle file changes (add/change)
            const handleFileChange = async (changedPath) => {
                for (const config of copyConfigs) {
                    // Check if the changed file is the source or within the source directory
                    if (changedPath === config.src || (changedPath.startsWith(config.src + path.sep))) {
                        try {
                            if (changedPath === config.src) {
                                // If it's the exact source path, copy it directly
                                await fse.copy(config.src, config.dest, { overwrite: true });
                                console.log(`Updated ${config.dest}`);
                            } else {
                                // If it's a file within a directory, maintain the relative path
                                const relativePath = path.relative(config.src, changedPath);
                                const destPath = path.join(config.dest, relativePath);

                                await fse.ensureDir(path.dirname(destPath));
                                await fse.copy(changedPath, destPath, { overwrite: true });
                                console.log(`Updated ${destPath}`);
                            }
                        } catch (error) {
                            console.error(`Error updating ${changedPath}:`, error);
                        }
                        break;
                    }
                }
            };

            // Handle file deletions
            const handleFileDelete = async (changedPath) => {
                for (const config of copyConfigs) {
                    // Check if the deleted file is within a source directory
                    if (changedPath.startsWith(config.src + path.sep)) {
                        try {
                            const relativePath = path.relative(config.src, changedPath);
                            const destPath = path.join(config.dest, relativePath);

                            await fse.remove(destPath);
                            console.log(`Removed ${destPath}`);
                        } catch (error) {
                            console.error(`Error removing ${destPath}:`, error);
                        }
                        break;
                    }
                }
            };

            watcher.on('add', handleFileChange);
            watcher.on('change', handleFileChange);
            watcher.on('unlink', handleFileDelete);
        }
    }
}

function updateTsConfig(isDev) {
    const tsConfigPath = path.join(__dirname, 'tsconfig.json');
    let tsConfig = JSON.parse(fs.readFileSync(tsConfigPath, 'utf8'));

    if (!tsConfig._originalCompilerOptions && isDev) {
        tsConfig._originalCompilerOptions = {...tsConfig.compilerOptions};
    }

    if (isDev) {
        tsConfig.compilerOptions = {
            ...tsConfig.compilerOptions,
            sourceMap: true,
            inlineSources: true
        };
    } else if (tsConfig._originalCompilerOptions) {
        // Restore original values
        tsConfig.compilerOptions = {...tsConfig._originalCompilerOptions};
        delete tsConfig._originalCompilerOptions;
    }
    fs.writeFileSync(tsConfigPath, JSON.stringify(tsConfig, null, 2) + '\n');
    console.log(`Updated tsconfig.json for ${isDev ? 'development' : 'production'} mode`);
}

function cleanup() {
    console.log('\nRestoring tsconfig.json...');
    updateTsConfig(false);
}

// Handle various exit scenarios
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', () => {
    try {
        updateTsConfig(false);
    } catch (error) {
        console.error('Error restoring tsconfig.json during exit:', error);
    }
});

async function typecheck() {
    return new Promise((resolve, reject) => {
        const configPath = path.join(__dirname, 'tsconfig.json');
        const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
        const parsedConfig = ts.parseJsonConfigFileContent(
            configFile.config,
            ts.sys,
            path.dirname(configPath)
        );

        const program = ts.createProgram({
            rootNames: parsedConfig.fileNames,
            options: parsedConfig.options,
        });

        const diagnostics = ts.getPreEmitDiagnostics(program);

        if (diagnostics.length > 0) {
            const formatHost = {
                getCanonicalFileName: path => path,
                getCurrentDirectory: ts.sys.getCurrentDirectory,
                getNewLine: () => ts.sys.newLine
            };

            const messages = ts.formatDiagnosticsWithColorAndContext(
                diagnostics,
                formatHost
            );

            reject(new Error(`TypeScript type checking failed:\n${messages}`));
        } else {
            resolve();
        }
    });
}

async function build() {
    try {
        // Clear output folder
        clearFolder('dist');
        clearFolder('dist_ff');

        // Run type checking first
        await typecheck();

        // Update tsconfig.json based on mode
        updateTsConfig(dev);

        // Copy assets
        // Chromium-based
        await copyAssets(assetsToCopy['chrome'], watch, false);
        // Firefox
        await copyAssets(assetsToCopy['firefox'], watch, true);

        if (watch) {
            // Watch mode using context
            const contexts = await Promise.all([
                // Content script
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['content-script/js/content-script.ts'],
                    outfile: 'dist/content-script/js/content-script.js',
                }),
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['content-script/js/content-script.ts'],
                    outfile: 'dist_ff/content-script/js/content-script.js',
                }),
                // Background script
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['background/js/background.ts'],
                    outfile: 'dist/background/js/background.js',
                }),
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['background/js/background.ts'],
                    outfile: 'dist_ff/background/js/background.js',
                }),
                // Popup script
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['popup/js/popup.ts'],
                    outfile: 'dist/popup/js/popup.js',
                }),
                esbuild.context({
                    ...commonConfig,
                    entryPoints: ['popup/js/popup.ts'],
                    outfile: 'dist_ff/popup/js/popup.js',
                }),
            ]);

            // Start watching
            await Promise.all(contexts.map(context => context.watch()));
            console.log('Watching for changes...');
            console.log(dev ? 'Development mode: Source maps enabled, minification disabled' : 'Production mode');
        } else {
            // One-time build
            await Promise.all([
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['content-script/js/content-script.ts'],
                    outfile: 'dist/content-script/js/content-script.js',
                }),
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['content-script/js/content-script.ts'],
                    outfile: 'dist_ff/content-script/js/content-script.js',
                }),
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['background/js/background.ts'],
                    outfile: 'dist/background/js/background.js',
                }),
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['background/js/background.ts'],
                    outfile: 'dist_ff/background/js/background.js',
                }),
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['popup/js/popup.ts'],
                    outfile: 'dist/popup/js/popup.js',
                }),
                esbuild.build({
                    ...commonConfig,
                    entryPoints: ['popup/js/popup.ts'],
                    outfile: 'dist_ff/popup/js/popup.js',
                }),
            ]);
            console.log('Build complete');
            console.log(dev ? 'Development mode: Source maps enabled, minification disabled' : 'Production mode');
        }
    } catch (error) {
        console.error('Build failed:', error);
        if (error.errors) {
            error.errors.forEach(err => {
                console.error(`${err.location.file}:${err.location.line}:${err.location.column} - ${err.text}`);
            });
        }
        process.exit(1);
    }
}

build();

