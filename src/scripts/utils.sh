git_summary () {
    git_summary=$1/git_summary.txt
    patch=$1/uncommited_changes.patch
    date > $git_summary
    printf "branch: " >> $git_summary
    git rev-parse --abbrev-ref HEAD >> $git_summary
    printf "commit: " >> $git_summary
    git rev-parse HEAD >> $git_summary
    git diff HEAD > $patch
}


