# Set Ollama CPU affinity to (CPU count - 4) cores
# Leaves 4 cores free for web server
$totalCores = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors
$useCores = [Math]::Max(1, $totalCores - 4)
$affinityMask = [Math]::Pow(2, $useCores) - 1

Write-Host "System has $totalCores cores, limiting Ollama to $useCores cores (reserving 4)"

$procs = Get-Process ollama -ErrorAction SilentlyContinue
foreach ($proc in $procs) {
    $proc.ProcessorAffinity = [int]$affinityMask
    Write-Host "Set affinity for process $($proc.Id) to $useCores cores"
}
