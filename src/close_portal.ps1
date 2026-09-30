param([switch]$DryRun)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class PortalWindow{[DllImport("user32.dll")]public static extern bool IsIconic(IntPtr h);[DllImport("user32.dll")]public static extern bool ShowWindowAsync(IntPtr h,int n);}'
$scope=[System.Windows.Automation.TreeScope]::Descendants
$walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
function IsPortal($value) {
    if($value -notmatch '^https?://'){$value='http://'+$value}
    $uri=$null
    return ([uri]::TryCreate($value,[UriKind]::Absolute,[ref]$uri) -and $uri.Scheme -in @('http','https') -and $uri.Host -eq '172.16.2.100' -and $uri.Port -in @(80,443,801))
}
function OutsideDocument($element,$root) {
    $node=$element
    for($i=0;$i -lt 30 -and $null -ne $node;$i++) {
        if($node.Current.ControlType -eq [System.Windows.Automation.ControlType]::Document){return $false}
        if([System.Windows.Automation.Automation]::Compare($node,$root)){return $true}
        $node=$walker.GetParent($node)
    }
    return $false
}
$matched=0;$closed=0;$errors=0;$portalAddresses=0;$selectedTabs=0
foreach($process in (Get-Process -Name msedge,chrome,firefox -ErrorAction SilentlyContinue)) {
    if($process.MainWindowHandle -eq 0){continue}
    $restored=$false;$closedBefore=$closed
    try {
        if(-not $DryRun -and [PortalWindow]::IsIconic($process.MainWindowHandle) -and $process.MainWindowTitle -match '上网登录窗|校园网认证|华东交通') {
            [void][PortalWindow]::ShowWindowAsync($process.MainWindowHandle,4)
            $restored=$true
            Start-Sleep -Milliseconds 200
        }
        $root=[System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
        $edits=$root.FindAll($scope,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Edit))
        $address=$null
        foreach($edit in $edits) {
            if($edit.Current.Name -notmatch '地址.*搜索|搜索.*地址|^地址栏$|Address.*(search|bar)|Search.*address' -and $edit.Current.AutomationId -notmatch '^(addressEditBox|urlbar-input)$'){continue}
            if(-not (OutsideDocument $edit $root)){continue}
            $value=$null
            if($edit.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$value) -and (IsPortal $value.Current.Value)){$address=$value;break}
        }
        if($null -eq $address){continue}
        $portalAddresses++
        $tabs=$root.FindAll($scope,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TabItem))
        foreach($tab in $tabs) {
            if(-not (OutsideDocument $tab $root)){continue}
            $selection=$null
            if(-not $tab.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$selection) -or -not $selection.Current.IsSelected){continue}
            $selectedTabs++
            $buttons=$tab.FindAll($scope,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
            foreach($button in $buttons) {
                if($button.Current.Name -notmatch '^(关闭标签页|关闭选项卡|关闭|Close tab|Close)(?:$|[\s（(,，:：])'){continue}
                $invoke=$null
                $legacy=$null
                $canInvoke=$button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$invoke)
                if(-not $canInvoke -and -not $button.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern,[ref]$legacy)){continue}
                $matched++
                if(-not $DryRun -and $selection.Current.IsSelected -and (IsPortal $address.Current.Value)) {
                    if($canInvoke){$invoke.Invoke()}else{$legacy.DoDefaultAction()}
                    $closed++
                }
                break
            }
            break
        }
    } catch {$errors++} finally {
        if($restored -and $closed -eq $closedBefore){[void][PortalWindow]::ShowWindowAsync($process.MainWindowHandle,6)}
    }
}
@{matched=$matched;closed=$closed;errors=$errors;portalAddresses=$portalAddresses;selectedTabs=$selectedTabs}|ConvertTo-Json -Compress
