# PortfolioAlpha Windows Scheduled Tasks Setup
# Run as: powershell -ExecutionPolicy Bypass -File deploy\windows\setup_tasks.ps1

$root = "C:\ngen26ABG\PortfolioAlpha"
$tasks = @(
    @{Name="Data Sync"; Time="08:00"; Script="agents\data_sync.py"; Args="--daily"},
    @{Name="Stock Selection"; Time="08:30"; Script="agents\stock_selection.py"; Args=""},
    @{Name="Live Trader"; Time="09:42"; Script="agents\live_trader.py"; Args=""}
)

foreach ($t in $tasks) {
    $tn = "SwingPortfolio\$($t.Name)"
    $cmd = "python"
    $args = "`"$root\$($t.Script)`" $($t.Args)"
    schtasks /Create /TN $tn /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST $($t.Time) /TR "$cmd $args" /F
}
Write-Output "`nTasks created. Verify:"
schtasks /Query /TN "SwingPortfolio\*" /V /FO LIST 2>&1 | Select-String "TaskName|Task To Run|Schedule Type"
