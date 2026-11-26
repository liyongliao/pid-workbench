// Static-file deployments also enter the shared model workspace.
const target=new URL(location.href);
target.pathname='/nwd.html';
target.searchParams.set('workspace','twin');
location.replace(target);
